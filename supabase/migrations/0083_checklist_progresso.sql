-- 0083_checklist_progresso.sql  (Progresso parcial por FOLHA — alimentado pelas medições do diário)
--
-- Generaliza o progresso do checklist de BINÁRIO (estado concluido sim/não) p/ PERCENTUAL por folha.
-- `checklist_itens.progresso_pct` é uma DENORMALIZAÇÃO (cache) da última medição (0082) por data do
-- diário; a fonte de verdade é `diario_tarefas`. null = sem medição → o front/cálculo caem no estado
-- (concluido=100, senão 0). `estado` continua existindo (atalho grosso / curva-S fallback) e é mantido
-- coerente com progresso_pct. Aplicar como postgres, DEPOIS da 0082. DEV antes de PROD.

begin;

-- ===================== (a) coluna denormalizada =====================
alter table public.checklist_itens
  add column if not exists progresso_pct numeric(5,2)
    check (progresso_pct is null or (progresso_pct >= 0 and progresso_pct <= 100));

-- ===================== (b) sincronização progresso_pct ↔ estado (FONTE ÚNICA) =====================
-- Recalcula a coluna denormalizada do item a partir da ÚLTIMA medição (por data do diário, tie-break
-- created_at) e SINCRONIZA o estado: 0→pendente, 100→concluido (concluido_em = DATA DO DIÁRIO, não now()),
-- entre→em_andamento. SEM medição → zera só a coluna e PRESERVA estado/conclusão manuais (checkbox).
-- SECURITY DEFINER: chamada pelo service (cria_app, após gravar a medição) E pelo gatilho de recálculo
-- no DELETE (inclui CASCADE de diário/tarefa, que não passa pelo service). O UPDATE interno dispara o
-- checklist_itens_guard normalmente (só mexe em progresso_pct/estado/concluido_* → dentro da allowlist).
create or replace function public.recalcular_progresso_item(p_item uuid)
returns void
language plpgsql security definer set search_path = '' as $$
declare
  m_pct  numeric(5,2);
  m_data date;
  m_by   uuid;
begin
  select dt.progresso_pct, d.data, dt.created_by
    into m_pct, m_data, m_by
  from public.diario_tarefas dt
  join public.diario_obra d on d.id = dt.diario_id
  where dt.item_id = p_item
  order by d.data desc, dt.created_at desc
  limit 1;

  if not found then
    -- item pode estar mid-delete (CASCADE) → o WHERE casa nenhuma linha (no-op seguro).
    update public.checklist_itens
       set progresso_pct = null
     where id = p_item and progresso_pct is not null;
    return;
  end if;

  update public.checklist_itens i set
    progresso_pct = m_pct,
    estado = (case when m_pct >= 100 then 'concluido'
                   when m_pct <= 0   then 'pendente'
                   else 'em_andamento' end)::public.estado_item,
    concluido_em  = case when m_pct >= 100 then m_data::timestamptz else null end,
    concluido_por = case when m_pct >= 100 then m_by else null end
  where i.id = p_item;
end;
$$;
alter function public.recalcular_progresso_item(uuid) owner to postgres;
grant execute on function public.recalcular_progresso_item(uuid) to cria_app;

-- ===================== (c) gatilho de recálculo no DELETE de medição =====================
-- Apagar um diário/tarefa via CASCADE NÃO passa pelo service → sem isto a coluna denormalizada ficaria
-- defasada (apontando uma medição que sumiu). AFTER DELETE recalcula o item afetado. (No DELETE
-- explícito via service o recálculo já é feito lá; este gatilho é idempotente — recalcula de novo.)
create or replace function public.diario_tarefas_recalc()
returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  perform public.recalcular_progresso_item(old.item_id);
  return old;
end;
$$;
alter function public.diario_tarefas_recalc() owner to postgres;
drop trigger if exists trg_diario_tarefas_recalc on public.diario_tarefas;
create trigger trg_diario_tarefas_recalc
  after delete on public.diario_tarefas
  for each row execute function public.diario_tarefas_recalc();

-- ===================== (d) recriar checklist_itens_guard (base VIVA 0081 + 2 deltas) =====================
-- Cópia INTEGRAL do 0081 com SÓ dois acréscimos:
--   (1) allowlist do prestador no UPDATE ganha 'progresso_pct' (a medição mexe nessa coluna);
--   (2) poka-yoke: não criar SubTarefa sob uma Tarefa que JÁ TEM medição (ela viraria agregador e o
--       avanço medido na folha ficaria órfão) — espelha o bloqueio de "tarefa com dependência".
create or replace function public.checklist_itens_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    if not exists (select 1 from public.etapas e
                   where e.id = new.etapa_id and e.obra_id = new.obra_id) then
      raise exception 'etapa nao pertence a obra do item' using errcode = '23514';
    end if;
    -- subetapa (quando setada): tem de ser da MESMA etapa/obra do item (coerência Etapa->Subetapa->Tarefa).
    if new.subetapa_id is not null then
      if not exists (select 1 from public.subetapas s
                     where s.id = new.subetapa_id
                       and s.etapa_id = new.etapa_id
                       and s.obra_id = new.obra_id) then
        raise exception 'subetapa nao pertence a etapa/obra do item' using errcode = '23514';
      end if;
    end if;
    -- sub-item: pai existe, na mesma etapa/obra, é top-level (só 2 níveis de item) e na MESMA subetapa
    -- (a SubTarefa mora onde a Tarefa mora).
    if new.parent_item_id is not null then
      if not exists (select 1 from public.checklist_itens pai
                     where pai.id = new.parent_item_id
                       and pai.etapa_id = new.etapa_id
                       and pai.obra_id = new.obra_id
                       and pai.parent_item_id is null
                       and pai.subetapa_id is not distinct from new.subetapa_id) then
        raise exception 'sub-item: pai invalido (outra etapa/obra/subetapa ou ja e sub-item)'
          using errcode = '23514';
      end if;
      -- trava a linha da Tarefa-pai p/ SERIALIZAR com um INSERT concorrente de dependência/medição
      -- nessa tarefa: as duas txns competem por esta linha, então cada uma enxerga o commit da outra e
      -- a invariante "ponta de dependência / folha medida é FOLHA" não escapa por TOCTOU.
      perform 1 from public.checklist_itens where id = new.parent_item_id for update;
      -- a Tarefa-pai não pode ser ponta de dependência (a dependência tem de ficar numa FOLHA).
      if exists (select 1 from public.tarefa_dependencias d
                 where d.predecessora_id = new.parent_item_id
                    or d.sucessora_id = new.parent_item_id) then
        raise exception 'tarefa com dependencia nao pode receber subtarefa; remova a dependencia primeiro'
          using errcode = '23514';
      end if;
      -- a Tarefa-pai não pode ter MEDIÇÃO de avanço no diário (viraria agregador e o avanço medido na
      -- folha ficaria órfão) — remova as medições antes de quebrar a tarefa em subtarefas.
      if exists (select 1 from public.diario_tarefas dt where dt.item_id = new.parent_item_id) then
        raise exception 'tarefa com avanco lancado no diario nao pode receber subtarefa; remova as medicoes primeiro'
          using errcode = '23514';
      end if;
    end if;
    -- equipe é nível-tenant: só pode apontar p/ equipe do MESMO tenant do item (anti cross-tenant).
    if new.equipe_id is not null
       and not exists (select 1 from public.equipes eq
                       where eq.id = new.equipe_id and eq.tenant_id = new.tenant_id) then
      raise exception 'equipe de outro tenant' using errcode = '42501';
    end if;
    if not public.is_arquiteto_ativo(new.obra_id) then
      raise exception 'apenas arquiteto pode criar item' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    -- identidade/escopo (inclui pai e subetapa) nunca mudam por UPDATE (vale até p/ arquiteto)
    if new.id is distinct from old.id
       or new.tenant_id is distinct from old.tenant_id
       or new.obra_id  is distinct from old.obra_id
       or new.etapa_id is distinct from old.etapa_id
       or new.subetapa_id is distinct from old.subetapa_id
       or new.parent_item_id is distinct from old.parent_item_id
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade/escopo do item sao imutaveis' using errcode = '42501';
    end if;
    -- equipe nova (quando muda) tem de ser do mesmo tenant (defensivo; o prestador nem chega aqui).
    if new.equipe_id is not null and new.equipe_id is distinct from old.equipe_id
       and not exists (select 1 from public.equipes eq
                       where eq.id = new.equipe_id and eq.tenant_id = new.tenant_id) then
      raise exception 'equipe de outro tenant' using errcode = '42501';
    end if;

    v_papel := public.meu_papel_obra(old.obra_id);
    if v_papel = 'arquiteto' then
      return new;
    elsif v_papel = 'prestador' then
      -- ALLOWLIST real: só estado/conclusão/PROGRESSO (e updated_at do trigger) variam; o resto é
      -- imutável p/ o prestador — inclusive datas, duracao_dias, orçamento, equipe_id, parent/subetapa.
      if (to_jsonb(new) - 'estado' - 'concluido_por' - 'concluido_em' - 'progresso_pct' - 'updated_at')
         is distinct from
         (to_jsonb(old) - 'estado' - 'concluido_por' - 'concluido_em' - 'progresso_pct' - 'updated_at')
      then
        raise exception 'prestador so pode alterar o estado/avanco do item' using errcode = '42501';
      end if;
      return new;
    else
      raise exception 'sem permissao para alterar item' using errcode = '42501';
    end if;
  end if;

  if not public.is_arquiteto_ativo(old.obra_id) then
    raise exception 'apenas arquiteto pode remover item' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.checklist_itens_guard() owner to postgres;
-- trigger trg_itens_guard (0025) já aponta p/ esta função; não recriar.

commit;
