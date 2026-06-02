-- 0002_obras.sql  (Fase 1)
-- Obras. tenant_id = arquiteto dono. id é UUID gerado NO CLIENTE (offline).
-- seq_humano (Obra #1, #2 por tenant) é atribuído no servidor pelo trigger (0005).

create table public.obras (
  id          uuid               primary key,         -- gerado no cliente
  tenant_id   uuid               not null references public.profiles(id) on delete restrict,
  nome        text               not null,
  status      public.status_obra not null default 'ativa',
  seq_humano  bigint,                                  -- preenchido pelo trigger BEFORE INSERT
  created_at  timestamptz        not null default now(),
  updated_at  timestamptz        not null default now()
);

-- rótulo humano único por tenant (defesa em profundidade do contador)
create unique index uq_obras_tenant_seq on public.obras (tenant_id, seq_humano);
create index ix_obras_tenant on public.obras (tenant_id);

create trigger trg_obras_updated_at
  before update on public.obras
  for each row execute function public.set_updated_at();
