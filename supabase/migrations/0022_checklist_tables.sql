-- 0022_checklist_tables.sql  (Fase 3 — Cronograma -> Checklist: tabelas)
-- etapa (stage) -> checklist_item (item), escopados a OBRA (nao projeto).
-- Dual-ID: id = UUID gerado no cliente (offline) + seq_humano por tenant (trigger 0023).
-- tenant_id DENORMALIZADO (seq por-tenant sem JOIN; espelha uq_obras_tenant_seq). Coerencia/
-- imutabilidade do tenant_id sao garantidas pelos guards (0025). nome_norm = chave natural de
-- dedupe do import (lower/sem acento/colapsa espacos; computado no backend, MESMA fn do import).

-- 3 estados fixos do item (poka-yoke, sem texto livre). Enum nomeado (padrao do 0001), mas
-- GUARDADO num DO block porque "create type" nao aceita "if not exists" (re-aplicavel DEV->PROD).
-- Transicoes sao ANY-TO-ANY (o "toggle" da UI pode ir em qualquer direcao); o ciclo natural
-- pendente->em_andamento->concluido e so convencao de exibicao, NAO e imposto no banco.
do $$
begin
  if not exists (
    select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
    where t.typname = 'estado_item' and n.nspname = 'public'
  ) then
    create type public.estado_item as enum ('pendente', 'em_andamento', 'concluido');
  end if;
end $$;

-- ===================== ETAPAS =====================
create table if not exists public.etapas (
  id          uuid        primary key,                              -- gerado no cliente
  obra_id     uuid        not null references public.obras(id)     on delete cascade,
  tenant_id   uuid        not null references public.profiles(id)  on delete restrict,
  nome        text        not null,
  nome_norm   text        not null,                                 -- chave de dedupe (por obra)
  ordem       int         not null default 0,                       -- ordenacao manual (drag)
  seq_humano  bigint,                                               -- preenchido pelo trigger (0023)
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- rotulo humano unico por tenant (defesa em profundidade do contador; espelha uq_obras_tenant_seq)
create unique index if not exists uq_etapas_tenant_seq    on public.etapas (tenant_id, seq_humano);
-- arvore por obra, ja ordenada
create index        if not exists ix_etapas_obra_ordem    on public.etapas (obra_id, ordem, created_at);
-- dedupe idempotente do import: 1 etapa por nome normalizado POR OBRA
create unique index if not exists uq_etapas_obra_nomenorm on public.etapas (obra_id, nome_norm);

drop trigger if exists trg_etapas_updated_at on public.etapas;
create trigger trg_etapas_updated_at
  before update on public.etapas
  for each row execute function public.set_updated_at();

-- ===================== ITENS =====================
-- obra_id e tenant_id DENORMALIZADOS: RLS por obra_id sem JOIN; seq por-tenant sem JOIN.
-- concluido_por/concluido_em = atribuicao desnormalizada (mostrar "concluido por Fulano" na arvore
-- sem varrer o audit_log); preenchidos/limpos no toggle, junto com o estado.
create table if not exists public.checklist_itens (
  id            uuid               primary key,                     -- gerado no cliente
  etapa_id      uuid               not null references public.etapas(id)   on delete cascade,
  obra_id       uuid               not null references public.obras(id)    on delete cascade,
  tenant_id     uuid               not null references public.profiles(id) on delete restrict,
  nome          text               not null,
  nome_norm     text               not null,                        -- dedupe do import (por etapa)
  estado        public.estado_item not null default 'pendente',
  concluido_por uuid               references public.profiles(id) on delete set null,
  concluido_em  timestamptz,
  ordem         int                not null default 0,
  seq_humano    bigint,
  created_at    timestamptz        not null default now(),
  updated_at    timestamptz        not null default now()
);

create unique index if not exists uq_itens_tenant_seq    on public.checklist_itens (tenant_id, seq_humano);
create index        if not exists ix_itens_etapa_ordem   on public.checklist_itens (etapa_id, ordem, created_at);
-- arvore por obra inteira (1 endpoint) sem item->etapa->obra
create index        if not exists ix_itens_obra          on public.checklist_itens (obra_id);
-- dedupe do import: 1 item por nome normalizado POR ETAPA
create unique index if not exists uq_itens_etapa_nomenorm on public.checklist_itens (etapa_id, nome_norm);

drop trigger if exists trg_itens_updated_at on public.checklist_itens;
create trigger trg_itens_updated_at
  before update on public.checklist_itens
  for each row execute function public.set_updated_at();
