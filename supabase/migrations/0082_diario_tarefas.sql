-- 0082_diario_tarefas.sql  (Diário encorpado — AVANÇO por tarefa lançado no diário)
--
-- Liga uma entrada do DIÁRIO (0066) a N TAREFAS (folhas do checklist) com uma MEDIÇÃO de avanço
-- datada (a data é a do diário). Modelo SNAPSHOT: progresso_pct = onde a folha ESTÁ naquela data
-- (não é incremento). Isto vira a fonte do progresso real da obra (contagem/etapa%/Gantt/curva-S).
-- Aplicar como postgres, DEPOIS da 0066/0081. DEV antes de PROD.
--
-- Esta migration cria SÓ a tabela-medição + guard + RLS. A coluna denormalizada
-- checklist_itens.progresso_pct, a função de sincronização e o gatilho de recálculo vêm na 0083
-- (dependem da coluna nova); a foto-por-tarefa (anexos parent_type='diario_tarefa' + legenda) vem na
-- 0084. Sem seq_humano: a medição é uma SUB-LINHA do diário (não é entidade referenciada por número),
-- logo NÃO entra no entity_seq_counters.

begin;

-- ===================== tabela diario_tarefas (molde = diario_obra 0066) =====================
create table if not exists public.diario_tarefas (
  id            uuid        primary key,                              -- gerado no cliente (dual-ID)
  diario_id     uuid        not null references public.diario_obra(id)     on delete cascade,
  item_id       uuid        not null references public.checklist_itens(id) on delete cascade,
  obra_id       uuid        not null references public.obras(id)           on delete cascade,  -- denorm RLS
  tenant_id     uuid        not null references public.profiles(id)        on delete restrict,
  progresso_pct numeric(5,2) not null check (progresso_pct >= 0 and progresso_pct <= 100),  -- a linha É a medição
  qtd_executada numeric(14,3)         check (qtd_executada is null or qtd_executada >= 0),   -- informativo (entrada por qtd)
  observacao    text,
  created_by    uuid        references public.profiles(id) on delete set null,  -- NÃO imutabilizar (lição 0066)
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (diario_id, item_id)                                         -- 1 medição por tarefa por diário
);
-- "última medição por data" e curva-S por item dependem de varrer por item_id.
create index if not exists ix_diario_tarefas_item on public.diario_tarefas (item_id);

drop trigger if exists trg_diario_tarefas_updated_at on public.diario_tarefas;
create trigger trg_diario_tarefas_updated_at
  before update on public.diario_tarefas for each row execute function public.set_updated_at();

-- ===================== guard (SECURITY DEFINER, owner postgres) =====================
-- Dispara ANTES de updated_at (nome '_guard' < '_updated_at'). INSERT: coerência tenant/obra; diário e
-- item são da MESMA obra; item é FOLHA (sem subtarefas) — trava a linha do item p/ serializar contra um
-- INSERT concorrente de subtarefa (anti-TOCTOU, igual 0081); quem executa a obra; prestador SÓ no
-- diário PRÓPRIO. UPDATE: identidade imutável (só progresso/qtd/observacao mudam); arquiteto qualquer /
-- prestador só no diário próprio. DELETE: igual ao UPDATE.
create or replace function public.diario_tarefas_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    if not exists (select 1 from public.diario_obra d
                   where d.id = new.diario_id and d.obra_id = new.obra_id) then
      raise exception 'diario nao pertence a obra da medicao' using errcode = '23514';
    end if;
    -- trava a linha do item p/ SERIALIZAR com um INSERT concorrente de subtarefa nesse item: as duas
    -- txns competem por esta linha → a invariante "tarefa medida é FOLHA" não escapa por TOCTOU.
    perform 1 from public.checklist_itens where id = new.item_id for update;
    if not exists (select 1 from public.checklist_itens i
                   where i.id = new.item_id and i.obra_id = new.obra_id) then
      raise exception 'tarefa da medicao nao pertence a obra' using errcode = '23514';
    end if;
    if exists (select 1 from public.checklist_itens c where c.parent_item_id = new.item_id) then
      raise exception 'so e possivel medir o avanco de uma folha (tarefa sem subtarefas)'
        using errcode = '23514';
    end if;
    if not public.pode_executar_obra(new.obra_id) then
      raise exception 'apenas quem executa a obra registra avanco' using errcode = '42501';
    end if;
    -- prestador só mede no diário que ele mesmo criou (espelha diario_obra_guard).
    if public.meu_papel_obra(new.obra_id) = 'prestador'
       and not exists (select 1 from public.diario_obra d
                       where d.id = new.diario_id
                         and d.created_by is not distinct from (select auth.uid())) then
      raise exception 'prestador so registra avanco no proprio diario' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    if new.id is distinct from old.id
       or new.diario_id is distinct from old.diario_id
       or new.item_id is distinct from old.item_id
       or new.obra_id is distinct from old.obra_id
       or new.tenant_id is distinct from old.tenant_id
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade da medicao e imutavel' using errcode = '42501';
    end if;
    v_papel := public.meu_papel_obra(old.obra_id);
    if v_papel = 'arquiteto' then
      return new;
    elsif v_papel = 'prestador'
          and exists (select 1 from public.diario_obra d
                      where d.id = old.diario_id
                        and d.created_by is not distinct from (select auth.uid())) then
      return new;  -- prestador edita medição só no diário PRÓPRIO
    else
      raise exception 'sem permissao para alterar esta medicao' using errcode = '42501';
    end if;
  end if;

  -- DELETE
  v_papel := public.meu_papel_obra(old.obra_id);
  if v_papel = 'arquiteto' then
    return old;
  elsif v_papel = 'prestador'
        and exists (select 1 from public.diario_obra d
                    where d.id = old.diario_id
                      and d.created_by is not distinct from (select auth.uid())) then
    return old;
  else
    raise exception 'sem permissao para apagar esta medicao' using errcode = '42501';
  end if;
end;
$$;
alter function public.diario_tarefas_guard() owner to postgres;
drop trigger if exists trg_diario_tarefas_guard on public.diario_tarefas;
create trigger trg_diario_tarefas_guard
  before insert or update or delete on public.diario_tarefas
  for each row execute function public.diario_tarefas_guard();

-- ===================== GRANTS + RLS (espelha diario_obra 0066) =====================
grant select, insert, update, delete on public.diario_tarefas to cria_app;
alter table public.diario_tarefas enable row level security;

drop policy if exists diario_tarefas_select on public.diario_tarefas;
create policy diario_tarefas_select on public.diario_tarefas
  for select to authenticated using ( obra_id in (select public.current_obra_ids()) );
drop policy if exists diario_tarefas_insert on public.diario_tarefas;
create policy diario_tarefas_insert on public.diario_tarefas
  for insert to authenticated with check ( public.pode_executar_obra(obra_id) );
drop policy if exists diario_tarefas_update on public.diario_tarefas;
create policy diario_tarefas_update on public.diario_tarefas
  for update to authenticated
  using ( public.pode_executar_obra(obra_id) ) with check ( public.pode_executar_obra(obra_id) );
drop policy if exists diario_tarefas_delete on public.diario_tarefas;
create policy diario_tarefas_delete on public.diario_tarefas
  for delete to authenticated using ( public.pode_executar_obra(obra_id) );

commit;
