-- 0034_projeto_tables.sql  (Fase 5 — Módulo de Projeto: tabelas de identidade + vínculo)
-- PROJETO ≠ OBRA (decisão travada): entidades separadas e relacionadas. Projeto pode anteceder/
-- originar uma obra e PODE existir SEM obra. [USUÁRIO] Projeto é ESPAÇO PRÓPRIO: tem membros e
-- código próprios (espelha a máquina de vínculo da Fase 1: obra_membros/obra_codigos), estados
-- pendente/ativo, e link OPCIONAL a uma obra (projetos.obra_id nullable, cardinalidade 1:1).
-- Reusa os enums papel_obra/estado_membro (0001). Prestador NÃO participa de projeto (guard 0040).

-- enum de status da revisão (poka-yoke; usado em 0035). DO block: "create type" não aceita "if not
-- exists" (re-aplicável DEV→PROD).
do $$
begin
  if not exists (
    select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
    where t.typname = 'status_revisao' and n.nspname = 'public'
  ) then
    create type public.status_revisao as enum ('pendente', 'aprovado', 'alteracao_pedida', 'recusado');
  end if;
end $$;

-- ===================== PROJETOS =====================
create table if not exists public.projetos (
  id          uuid        primary key,                                -- gerado no cliente (offline)
  tenant_id   uuid        not null references public.profiles(id) on delete restrict,
  obra_id     uuid        references public.obras(id) on delete set null,  -- link OPCIONAL (1:1)
  nome        text        not null,
  briefing    jsonb       not null default '{}'::jsonb,               -- onboarding (estruturado no front)
  -- alterações INCLUÍDAS no contrato com o cliente — parâmetro do ARQUITETO por projeto (não é eixo
  -- de plano free/pro). NULL = não controla (nunca sinaliza). "além do incluído" = numero > este valor.
  revisoes_incluidas int    check (revisoes_incluidas is null or revisoes_incluidas >= 0),
  seq_humano  bigint,                                                 -- trigger (0037)
  created_by  uuid        not null references public.profiles(id) on delete restrict,  -- histórico
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create unique index if not exists uq_projetos_tenant_seq on public.projetos (tenant_id, seq_humano);
-- 1 obra origina-se de no MÁXIMO 1 projeto (parcial: NULL é o caso comum). Coerência de tenant do
-- vínculo obra↔projeto é imposta pelo guard 0040.
create unique index if not exists uq_projetos_obra on public.projetos (obra_id) where obra_id is not null;
create index        if not exists ix_projetos_tenant on public.projetos (tenant_id);

drop trigger if exists trg_projetos_updated_at on public.projetos;
create trigger trg_projetos_updated_at
  before update on public.projetos
  for each row execute function public.set_updated_at();

-- ===================== PROJETO_MEMBROS (espelha obra_membros 0003) =====================
create table if not exists public.projeto_membros (
  id          uuid                 primary key default gen_random_uuid(),
  projeto_id  uuid                 not null references public.projetos(id) on delete cascade,
  profile_id  uuid                 not null references public.profiles(id) on delete cascade,
  papel       public.papel_obra    not null,                          -- só arquiteto/cliente (guard 0040)
  estado      public.estado_membro not null default 'pendente',
  invited_by  uuid                 references public.profiles(id) on delete set null,
  created_at  timestamptz          not null default now(),
  updated_at  timestamptz          not null default now(),
  constraint uq_projeto_membro unique (projeto_id, profile_id)        -- 1 vínculo por par
);

create index if not exists ix_projeto_membros_profile_estado on public.projeto_membros (profile_id, estado);
create index if not exists ix_projeto_membros_projeto        on public.projeto_membros (projeto_id);

drop trigger if exists trg_projeto_membros_updated_at on public.projeto_membros;
create trigger trg_projeto_membros_updated_at
  before update on public.projeto_membros
  for each row execute function public.set_updated_at();

-- ===================== PROJETO_CODIGOS (espelha obra_codigos 0006) =====================
create table if not exists public.projeto_codigos (
  id          uuid              primary key default gen_random_uuid(),
  projeto_id  uuid              not null references public.projetos(id) on delete cascade,
  codigo      text              not null,                             -- token curto (gerado no backend)
  papel       public.papel_obra not null,                            -- papel concedido (cliente; guard 0040)
  expires_at  timestamptz       not null,                            -- now() + 24h
  revoked_at  timestamptz,
  created_by  uuid              not null references public.profiles(id) on delete restrict,
  created_at  timestamptz       not null default now(),
  updated_at  timestamptz       not null default now()
);

create unique index if not exists uq_projeto_codigo_ativo on public.projeto_codigos (projeto_id) where revoked_at is null;
create unique index if not exists uq_projeto_codigo_valor on public.projeto_codigos (codigo);
create index        if not exists ix_projeto_codigos_projeto on public.projeto_codigos (projeto_id);

drop trigger if exists trg_projeto_codigos_updated_at on public.projeto_codigos;
create trigger trg_projeto_codigos_updated_at
  before update on public.projeto_codigos
  for each row execute function public.set_updated_at();
