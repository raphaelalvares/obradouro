-- 0080_subetapas.sql  (EAP 4 níveis — nova tabela SUBETAPA, entre Etapa e Tarefa)
--
-- A EAP passa de 3 p/ 4 níveis: Etapa -> Subetapa -> Tarefa -> SubTarefa. A SUBETAPA é um AGRUPADOR
-- (como a etapa): NÃO carrega custo nem estado próprios; agrega (custo/progresso/datas derivam dos
-- descendentes na leitura, no backend). Mas, como QUALQUER agregador pode ser FOLHA quando vazio (não
-- tem tarefas), ela ganha as MESMAS colunas de "marco-folha" que a etapa já tem (data_inicio/data_fim
-- do 0056 + concluida/concluida_em/concluida_por do 0057) — usadas só quando a subetapa está vazia.
--
-- Ragged: a Tarefa pertence OPCIONALMENTE a uma subetapa (checklist_itens.subetapa_id nullable, no
-- 0081); Etapa -> Tarefa direto (sem subetapa) continua válido.
--
-- Esta migration espelha o pacote da ETAPA: tabela (0022) + seq POR-OBRA (0055) + guard (0025) + RLS/
-- grants (0024) + updated_at. NÃO toca entity_seq_counters (a subetapa tem contador próprio por-obra,
-- como a etapa desde 0055). Aplicar como postgres, ANTES da 0081. DEV antes de PROD.

begin;

-- ===================== (1) TABELA =====================
-- id = UUID do cliente (dual-ID, offline). tenant_id/obra_id DENORMALIZADOS (RLS/seq/guard sem JOIN,
-- espelha etapas). nome_norm = chave de dedupe (lower/sem acento/colapsa espaços; computada no backend,
-- MESMA fn do checklist). datas/conclusão próprias só valem quando a subetapa é folha (sem tarefas).
create table if not exists public.subetapas (
  id            uuid        primary key,                              -- gerado no cliente
  etapa_id      uuid        not null references public.etapas(id)    on delete cascade,
  obra_id       uuid        not null references public.obras(id)     on delete cascade,
  tenant_id     uuid        not null references public.profiles(id)  on delete restrict,
  nome          text        not null,
  nome_norm     text        not null,                                 -- dedupe (por etapa)
  ordem         int         not null default 0,                       -- ordenação manual (drag)
  seq_humano    bigint,                                               -- preenchido pelo trigger (por obra)
  data_inicio   date,                                                 -- usadas só quando sem tarefas
  data_fim      date,
  concluida     boolean     not null default false,                   -- marco (subetapa-folha sem tarefas)
  concluida_em  timestamptz,
  concluida_por uuid        references public.profiles(id) on delete set null,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- rótulo humano único por obra (defesa em profundidade do contador; espelha uq_etapas_obra_seq/0055)
create unique index if not exists uq_subetapas_obra_seq
  on public.subetapas (obra_id, seq_humano);
-- árvore por etapa, já ordenada
create index if not exists ix_subetapas_etapa_ordem
  on public.subetapas (etapa_id, ordem, created_at);
-- dedupe idempotente: 1 subetapa por nome normalizado POR ETAPA
create unique index if not exists uq_subetapas_etapa_nomenorm
  on public.subetapas (etapa_id, nome_norm);

drop trigger if exists trg_subetapas_updated_at on public.subetapas;
create trigger trg_subetapas_updated_at
  before update on public.subetapas
  for each row execute function public.set_updated_at();

-- ===================== (2) SEQ POR OBRA (espelha 0055) =====================
-- Contador por obra (reseta #1,#2,#3... por obra). RLS ON, sem policy e sem grant a cria_app → só o
-- trigger SECURITY DEFINER (owner postgres) escreve.
create table if not exists public.obra_subetapa_seq_counters (
  obra_id   uuid   not null references public.obras(id) on delete cascade,
  last_seq  bigint not null default 0,
  primary key (obra_id)
);
alter table public.obra_subetapa_seq_counters enable row level security;

create or replace function public.assign_subetapa_seq()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_seq bigint;
begin
  if new.seq_humano is not null then
    return new;                                  -- idempotente: retry que já carrega o seq não renumera
  end if;
  insert into public.obra_subetapa_seq_counters as c (obra_id, last_seq)
  values (new.obra_id, 1)
  on conflict (obra_id) do update set last_seq = c.last_seq + 1
  returning c.last_seq into v_seq;
  new.seq_humano := v_seq;
  return new;
end;
$$;
alter function public.assign_subetapa_seq() owner to postgres;

-- ===================== (3) GUARD (espelha etapas_guard/0025 + coerência etapa->subetapa) =====================
-- create/rename/reorder/delete SÓ arquiteto ativo; tenant/obra coerentes e imutáveis; a etapa-pai tem
-- de ser da MESMA obra (coerência Etapa->Subetapa). Owner postgres; SECURITY DEFINER p/ ler obras/etapas.
create or replace function public.subetapas_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    if not exists (select 1 from public.etapas e
                   where e.id = new.etapa_id and e.obra_id = new.obra_id) then
      raise exception 'etapa nao pertence a obra da subetapa' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo(new.obra_id) then
      raise exception 'apenas arquiteto pode criar subetapa' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    -- identidade/escopo (inclui a etapa-pai) nunca mudam por UPDATE (anti-reparent cross-etapa)
    if new.id is distinct from old.id
       or new.tenant_id is distinct from old.tenant_id
       or new.obra_id  is distinct from old.obra_id
       or new.etapa_id is distinct from old.etapa_id
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade/escopo da subetapa sao imutaveis' using errcode = '42501';
    end if;
    if not public.is_arquiteto_ativo(old.obra_id) then
      raise exception 'apenas arquiteto pode alterar subetapa' using errcode = '42501';
    end if;
    return new;
  end if;

  -- DELETE
  if not public.is_arquiteto_ativo(old.obra_id) then
    raise exception 'apenas arquiteto pode remover subetapa' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.subetapas_guard() owner to postgres;
-- triggers: _guard ANTES de _seq (ordem alfabética: a coerência de tenant/obra é validada antes de o
-- seq ser alocado), exatamente como nas etapas/itens.
drop trigger if exists trg_subetapas_guard on public.subetapas;
create trigger trg_subetapas_guard
  before insert or update or delete on public.subetapas
  for each row execute function public.subetapas_guard();

drop trigger if exists trg_subetapas_seq on public.subetapas;
create trigger trg_subetapas_seq
  before insert on public.subetapas
  for each row execute function public.assign_subetapa_seq();

-- ===================== (4) GRANTS + RLS (espelha etapas/0024) =====================
grant select, insert, update, delete on public.subetapas to cria_app;
-- obra_subetapa_seq_counters: NENHUM grant a cria_app (só o trigger SECURITY DEFINER mexe).
alter table public.subetapas enable row level security;

-- SELECT p/ qualquer membro ativo (arquiteto/cliente/prestador veem a árvore).
drop policy if exists subetapas_select on public.subetapas;
create policy subetapas_select on public.subetapas
  for select to authenticated
  using ( obra_id in (select public.current_obra_ids()) );

-- INSERT/UPDATE/DELETE: só arquiteto ativo (na própria RLS; o guard backstopa).
drop policy if exists subetapas_insert on public.subetapas;
create policy subetapas_insert on public.subetapas
  for insert to authenticated
  with check ( public.is_arquiteto_ativo(obra_id) );
drop policy if exists subetapas_update on public.subetapas;
create policy subetapas_update on public.subetapas
  for update to authenticated
  using      ( public.is_arquiteto_ativo(obra_id) )
  with check ( public.is_arquiteto_ativo(obra_id) );
drop policy if exists subetapas_delete on public.subetapas;
create policy subetapas_delete on public.subetapas
  for delete to authenticated
  using ( public.is_arquiteto_ativo(obra_id) );

commit;
