-- 0081_checklist_itens_subetapa.sql  (EAP 4 níveis — Tarefa sob Subetapa + dependência por FOLHA)
--
-- Liga a Tarefa à Subetapa (0080) e generaliza as regras de cronograma p/ o modelo "folha carrega o
-- trabalho". Aplicar como postgres, APÓS a 0080. DEV antes de PROD.
--
-- (a) checklist_itens.subetapa_id nullable (NULL = Tarefa direto na Etapa → ragged). etapa_id continua
--     NOT NULL e denormalizado (RLS/seq/dedupe/anexos sem JOIN). ON DELETE CASCADE: apagar a Subetapa
--     apaga suas Tarefas (e, por parent_item_id, as SubTarefas) — consistente com Etapa->itens; e evita
--     o risco de SET NULL violar o índice de dedupe ao "subir" tarefas de mesmo nome p/ a raiz da etapa.
-- (b) Dedupe top-level por ESCOPO: tarefa direto-na-etapa é única por (etapa_id, nome) e tarefa sob
--     subetapa é única por (subetapa_id, nome). SubTarefa (parent setado) segue por (parent, nome).
-- (c) checklist_itens_guard recriado da VERSÃO VIVA (0065): + coerência/imutabilidade de subetapa_id e
--     o poka-yoke "tarefa com dependência não recebe SubTarefa" (mantém a invariante: ponta de
--     dependência é sempre FOLHA).
-- (d) tarefa_dependencias_guard generalizado: as pontas deixam de ser "top-level" e passam a ser FOLHA
--     (item sem subtarefas) — a dependência/duração vale em qualquer folha de qualquer nível.

begin;

-- ===================== (a) coluna subetapa_id + índice =====================
alter table public.checklist_itens
  add column if not exists subetapa_id uuid
    references public.subetapas(id) on delete cascade;   -- NULL = tarefa direto na etapa
create index if not exists ix_itens_subetapa on public.checklist_itens (subetapa_id);

-- ===================== (b) dedupe top-level por ESCOPO (substitui 0044) =====================
-- O índice top-level do 0044 (etapa_id, nome_norm WHERE parent NULL) assumia que toda tarefa pendura
-- direto na etapa. Com subetapa, separa em DOIS namespaces parciais; o de filhos (parent setado) fica.
drop index if exists public.uq_itens_etapa_nomenorm_top;
create unique index if not exists uq_itens_etapa_nomenorm_top
  on public.checklist_itens (etapa_id, nome_norm)
  where parent_item_id is null and subetapa_id is null;          -- tarefa direto na etapa
create unique index if not exists uq_itens_subetapa_nomenorm_top
  on public.checklist_itens (subetapa_id, nome_norm)
  where parent_item_id is null and subetapa_id is not null;      -- tarefa sob subetapa

-- ===================== (c) checklist_itens_guard (base 0065 + subetapa + folha-de-dependência) =====================
-- Idêntico ao 0065 (validação de pai top-level, imutabilidade, cross-tenant de equipe_id, allowlist
-- to_jsonb do prestador) MAIS: (1) coerência de subetapa_id (a subetapa é da MESMA etapa/obra do item);
-- (2) subetapa_id imutável (anti-reparent entre subetapas); (3) a SubTarefa herda a posição da Tarefa
-- (mesmo subetapa_id do pai); (4) não criar SubTarefa sob uma Tarefa que é PONTA de dependência (ela
-- viraria agregador e a dependência deixaria de estar numa folha) — remova a dependência antes.
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
      -- trava a linha da Tarefa-pai p/ SERIALIZAR com um INSERT concorrente de dependência nessa
      -- tarefa: as duas txns competem por esta linha, então cada uma enxerga o commit da outra e a
      -- invariante "ponta de dependência é FOLHA" não escapa por TOCTOU (vale até via PostgREST).
      perform 1 from public.checklist_itens where id = new.parent_item_id for update;
      -- a Tarefa-pai não pode ser ponta de dependência (a dependência tem de ficar numa FOLHA).
      if exists (select 1 from public.tarefa_dependencias d
                 where d.predecessora_id = new.parent_item_id
                    or d.sucessora_id = new.parent_item_id) then
        raise exception 'tarefa com dependencia nao pode receber subtarefa; remova a dependencia primeiro'
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
      -- ALLOWLIST real: só estado/conclusão (e updated_at do trigger) variam; o resto é imutável p/ o
      -- prestador — inclusive datas, duracao_dias, orçamento, equipe_id, parent_item_id e subetapa_id.
      if (to_jsonb(new) - 'estado' - 'concluido_por' - 'concluido_em' - 'updated_at')
         is distinct from
         (to_jsonb(old) - 'estado' - 'concluido_por' - 'concluido_em' - 'updated_at')
      then
        raise exception 'prestador so pode alterar o estado do item' using errcode = '42501';
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

-- ===================== (c.1) saneamento de arestas legadas (ponta = agregador) =====================
-- Sob 0061 uma Tarefa top-level COM subtarefas era ponta de dependência VÁLIDA. A partir daqui a ponta
-- TEM de ser FOLHA. Remove as arestas cuja ponta deixou de ser folha (ganhou subtarefas) — senão o
-- recálculo trataria um agregador como folha-na-rede e corromperia as datas a jusante. Idempotente; em
-- base nova é no-op. (As arestas válidas — ambas as pontas folha — são preservadas.)
delete from public.tarefa_dependencias d
where exists (select 1 from public.checklist_itens c where c.parent_item_id = d.predecessora_id)
   or exists (select 1 from public.checklist_itens c where c.parent_item_id = d.sucessora_id);

-- ===================== (d) tarefa_dependencias_guard: pontas = FOLHA (substitui 0061) =====================
-- Antes: ambas as pontas tinham de ser top-level (parent_item_id IS NULL). Agora a dependência vale em
-- qualquer FOLHA (item sem subtarefas), em qualquer nível (Tarefa-folha OU SubTarefa-folha). A
-- invariante "ponta é folha" é mantida pelo guard do item acima (não deixa uma ponta virar agregador).
-- Tudo o mais (coerência tenant/obra, só arquiteto, anti-ciclo, imutabilidade no UPDATE) é idêntico.
create or replace function public.tarefa_dependencias_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    -- trava as linhas das PONTAS p/ SERIALIZAR com um INSERT concorrente de subtarefa numa ponta:
    -- cada txn vê o commit da outra → a invariante "ponta é FOLHA" não escapa por TOCTOU.
    perform 1 from public.checklist_itens
      where id in (new.predecessora_id, new.sucessora_id) for update;
    -- predecessora: item da obra E folha (sem subtarefas)
    if not exists (select 1 from public.checklist_itens i
                   where i.id = new.predecessora_id and i.obra_id = new.obra_id) then
      raise exception 'predecessora nao pertence a obra' using errcode = '23514';
    end if;
    if exists (select 1 from public.checklist_itens c where c.parent_item_id = new.predecessora_id) then
      raise exception 'predecessora deve ser uma folha (sem subtarefas)' using errcode = '23514';
    end if;
    -- sucessora: item da obra E folha (sem subtarefas)
    if not exists (select 1 from public.checklist_itens i
                   where i.id = new.sucessora_id and i.obra_id = new.obra_id) then
      raise exception 'sucessora nao pertence a obra' using errcode = '23514';
    end if;
    if exists (select 1 from public.checklist_itens c where c.parent_item_id = new.sucessora_id) then
      raise exception 'sucessora deve ser uma folha (sem subtarefas)' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo(new.obra_id) then
      raise exception 'apenas arquiteto pode criar dependencia' using errcode = '42501';
    end if;
    -- anti-ciclo: a aresta nova ainda NÃO existe (BEFORE INSERT) → percorre só as arestas atuais.
    if exists (
      with recursive reach as (
        select d.sucessora_id as n
          from public.tarefa_dependencias d
          where d.predecessora_id = new.sucessora_id
        union
        select d.sucessora_id
          from public.tarefa_dependencias d
          join reach r on d.predecessora_id = r.n
      )
      select 1 from reach where n = new.predecessora_id
    ) then
      raise exception 'dependencia criaria um ciclo' using errcode = '23514';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    -- identidade/escopo imutáveis; só tipo/lag_dias podem mudar (arquiteto).
    if new.id is distinct from old.id
       or new.obra_id is distinct from old.obra_id
       or new.tenant_id is distinct from old.tenant_id
       or new.predecessora_id is distinct from old.predecessora_id
       or new.sucessora_id is distinct from old.sucessora_id
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade da dependencia e imutavel' using errcode = '42501';
    end if;
    if not public.is_arquiteto_ativo(old.obra_id) then
      raise exception 'apenas arquiteto pode alterar dependencia' using errcode = '42501';
    end if;
    return new;
  end if;

  -- DELETE
  if not public.is_arquiteto_ativo(old.obra_id) then
    raise exception 'apenas arquiteto pode remover dependencia' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.tarefa_dependencias_guard() owner to postgres;
-- trigger trg_tarefa_dependencias_guard (0061) já aponta p/ esta função; não recriar.

-- ===================== (e) importar_checklist: dedupe ciente do escopo subetapa =====================
-- Idêntica à versão viva (0044), com UMA correção: o exists-check do item passa a filtrar
-- `subetapa_id is null` (casa com o novo índice parcial uq_itens_etapa_nomenorm_top). O import segue
-- criando SÓ tarefas DIRETO na etapa (subetapa_id default NULL) — Subetapa é manual nesta fase. Sem o
-- filtro, uma tarefa manual de mesmo nome SOB uma subetapa mascararia a 1ª importação direto na etapa.
create or replace function public.importar_checklist(p_obra uuid, p_payload jsonb)
returns table (etapas_novas int, etapas_existentes int, itens_novos int, itens_existentes int)
language plpgsql security definer set search_path = '' as $$
declare
  v_uid      uuid := (select auth.uid());
  v_tenant   uuid;
  v_etapa    jsonb;
  v_item     jsonb;
  v_etapa_id uuid;
  v_nn       text;
  v_inn      text;
  v_seq      bigint;
begin
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;
  if jsonb_typeof(p_payload) is distinct from 'array' then
    raise exception 'payload de import invalido' using errcode = '22023';
  end if;

  select o.tenant_id into v_tenant from public.obras o where o.id = p_obra;
  if v_tenant is null then
    raise exception 'obra inexistente' using errcode = 'P0002';
  end if;
  if not public.is_arquiteto_ativo(p_obra) then
    raise exception 'apenas arquiteto pode importar' using errcode = '42501';
  end if;

  perform pg_advisory_xact_lock(hashtext('cria:import_checklist'), hashtext(p_obra::text));

  etapas_novas := 0; etapas_existentes := 0; itens_novos := 0; itens_existentes := 0;

  for v_etapa in select * from jsonb_array_elements(p_payload) loop
    v_nn := coalesce(v_etapa->>'nome_norm', '');
    if v_nn = '' then continue; end if;

    select e.id into v_etapa_id
    from public.etapas e where e.obra_id = p_obra and e.nome_norm = v_nn;

    if v_etapa_id is null then
      begin
        insert into public.etapas (id, obra_id, tenant_id, nome, nome_norm, ordem)
        values ((v_etapa->>'id')::uuid, p_obra, v_tenant,
                v_etapa->>'nome', v_nn, coalesce((v_etapa->>'ordem')::int, 0))
        returning id, seq_humano into v_etapa_id, v_seq;
        etapas_novas := etapas_novas + 1;
        perform public.cria_audit_log(null, null, p_obra, 'etapa.criada', 'etapa',
                                      v_etapa_id, null::jsonb, v_etapa->>'nome', v_seq, null);
      exception when unique_violation then
        select e.id into v_etapa_id
        from public.etapas e where e.obra_id = p_obra and e.nome_norm = v_nn;
        etapas_existentes := etapas_existentes + 1;
      end;
    else
      etapas_existentes := etapas_existentes + 1;
    end if;

    for v_item in select * from jsonb_array_elements(coalesce(v_etapa->'itens', '[]'::jsonb)) loop
      v_inn := coalesce(v_item->>'nome_norm', '');
      if v_inn = '' then continue; end if;

      -- dedupe no MESMO escopo da tarefa direto-na-etapa (parent null + subetapa null), casando com
      -- o índice parcial uq_itens_etapa_nomenorm_top da 0081.
      if exists (select 1 from public.checklist_itens ci
                 where ci.etapa_id = v_etapa_id and ci.nome_norm = v_inn
                       and ci.parent_item_id is null and ci.subetapa_id is null) then
        itens_existentes := itens_existentes + 1;
        continue;
      end if;

      begin
        insert into public.checklist_itens
          (id, etapa_id, obra_id, tenant_id, nome, nome_norm, ordem,
           ambiente, unidade, quantidade, custo_mao_obra, custo_material, custo_total)
        values ((v_item->>'id')::uuid, v_etapa_id, p_obra, v_tenant,
                v_item->>'nome', v_inn, coalesce((v_item->>'ordem')::int, 0),
                nullif(v_item->>'ambiente', ''),
                nullif(v_item->>'unidade', ''),
                nullif(v_item->>'quantidade', '')::numeric,
                nullif(v_item->>'custo_mao_obra', '')::numeric,
                nullif(v_item->>'custo_material', '')::numeric,
                nullif(v_item->>'custo_total', '')::numeric)
        returning seq_humano into v_seq;
        itens_novos := itens_novos + 1;
        perform public.cria_audit_log(null, null, p_obra, 'item.criado', 'checklist_item',
                                      (v_item->>'id')::uuid, null::jsonb, v_item->>'nome', v_seq,
                                      null);
      exception when unique_violation then
        itens_existentes := itens_existentes + 1;
      end;
    end loop;
  end loop;

  return next;
end;
$$;
alter function public.importar_checklist(uuid, jsonb) owner to postgres;
revoke all on function public.importar_checklist(uuid, jsonb) from public, anon;
grant execute on function public.importar_checklist(uuid, jsonb) to authenticated;

commit;
