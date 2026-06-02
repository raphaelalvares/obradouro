-- 0006_obra_codigos.sql  (Fase 1)
-- Código de obra (2ª porta de vínculo). Expira em 24h, revogável; um código ativo por obra.
-- "Uso único por pessoa" é consequência do unique(obra_id, profile_id) em obra_membros.

create table public.obra_codigos (
  id          uuid              primary key default gen_random_uuid(),
  obra_id     uuid              not null references public.obras(id) on delete cascade,
  codigo      text              not null,              -- token curto, legível (gerado no backend)
  papel       public.papel_obra not null,             -- papel concedido ao entrar
  expires_at  timestamptz       not null,             -- now() + interval '24 hours'
  revoked_at  timestamptz,                             -- revogação manual
  created_by  uuid              not null references public.profiles(id) on delete restrict,
  created_at  timestamptz       not null default now(),
  updated_at  timestamptz       not null default now()
);

-- um código ATIVO (não revogado) por obra; regenerar revoga o anterior (backend)
create unique index uq_obra_codigo_ativo on public.obra_codigos (obra_id) where revoked_at is null;
create unique index uq_obra_codigo_valor on public.obra_codigos (codigo);
create index ix_obra_codigos_obra on public.obra_codigos (obra_id);

create trigger trg_obra_codigos_updated_at
  before update on public.obra_codigos
  for each row execute function public.set_updated_at();
