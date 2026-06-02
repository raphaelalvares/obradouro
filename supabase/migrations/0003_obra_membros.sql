-- 0003_obra_membros.sql  (Fase 1)
-- Associação pessoa<->obra. Tenant e PAPEL vivem aqui (não no profile).
-- Uma pessoa pode estar em várias obras com papéis diferentes.

create table public.obra_membros (
  id          uuid                 primary key default gen_random_uuid(),
  obra_id     uuid                 not null references public.obras(id)    on delete cascade,
  profile_id  uuid                 not null references public.profiles(id) on delete cascade,
  papel       public.papel_obra    not null,
  estado      public.estado_membro not null default 'pendente',
  invited_by  uuid                 references public.profiles(id) on delete set null,
  created_at  timestamptz          not null default now(),
  updated_at  timestamptz          not null default now(),
  constraint uq_obra_membro unique (obra_id, profile_id)   -- 1 vínculo por par
);

-- Índices que SUSTENTAM a RLS (críticos para performance):
create index ix_obra_membros_profile_estado on public.obra_membros (profile_id, estado);
create index ix_obra_membros_obra           on public.obra_membros (obra_id);

create trigger trg_obra_membros_updated_at
  before update on public.obra_membros
  for each row execute function public.set_updated_at();
