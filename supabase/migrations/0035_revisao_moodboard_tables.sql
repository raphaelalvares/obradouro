-- 0035_revisao_moodboard_tables.sql  (Fase 5 — ciclo de revisões + moodboard)
-- REVISÃO = documento versionado FORMAL com ciclo de vida (status + motivo), DISTINTO do anexo de
-- foto (Fase 4, informal). Os BYTES vivem no StorageBackend (revisao_arquivos/moodboard_itens),
-- aqui só metadado + chaves opacas. numero (R0,R1…) é alocado pela RPC subir_revisao (0041) sob
-- advisory lock; só UMA revisão pendente por projeto (índice parcial). A sinalização "além do
-- incluído" é calculada AO VIVO (projetos.revisoes_incluidas vs numero) — NÃO há coluna congelada;
-- é INFORMACIONAL e NUNCA trava (o fato do momento fica no audit, imutável).

-- ===================== REVISOES =====================
create table if not exists public.revisoes (
  id               uuid                 primary key,                  -- gerado no cliente (offline)
  projeto_id       uuid                 not null references public.projetos(id) on delete cascade,
  tenant_id        uuid                 not null references public.profiles(id) on delete restrict,
  numero           int                  not null,                     -- R0..Rn (RPC sob lock)
  titulo           text,
  status           public.status_revisao not null default 'pendente',
  motivo           text,                                              -- razão de alteração/recusa (cliente)
  decidido_por     uuid                 references public.profiles(id) on delete set null,
  decidido_em      timestamptz,
  seq_humano       bigint,                                            -- trigger (0037)
  created_by       uuid                 not null references public.profiles(id) on delete restrict,
  created_at       timestamptz          not null default now(),
  updated_at       timestamptz          not null default now()
);

create unique index if not exists uq_revisoes_projeto_numero on public.revisoes (projeto_id, numero);
-- INVARIANTE: no máximo UMA revisão pendente por projeto (rede final, além do check sob lock na RPC)
create unique index if not exists uq_revisao_pendente on public.revisoes (projeto_id) where status = 'pendente';
create unique index if not exists uq_revisoes_tenant_seq on public.revisoes (tenant_id, seq_humano);
create index        if not exists ix_revisoes_projeto on public.revisoes (projeto_id, numero);

drop trigger if exists trg_revisoes_updated_at on public.revisoes;
create trigger trg_revisoes_updated_at
  before update on public.revisoes
  for each row execute function public.set_updated_at();

-- ===================== REVISAO_ARQUIVOS (mídia da revisão; IMUTÁVEL, espelha anexos 0028) =====================
-- projeto_id/tenant_id DENORMALIZADOS (RLS por projeto sem JOIN; quota por tenant sem JOIN).
-- is_pdf: PDF não passa pelo imaging (sem thumb → thumb_key NULL); imagem gera thumb.
create table if not exists public.revisao_arquivos (
  id            uuid        primary key,                              -- gerado no cliente
  revisao_id    uuid        not null references public.revisoes(id)  on delete cascade,
  projeto_id    uuid        not null references public.projetos(id)  on delete cascade,
  tenant_id     uuid        not null references public.profiles(id)  on delete restrict,
  nome_arquivo  text        not null,
  content_type  text        not null,
  tamanho_bytes bigint      not null check (tamanho_bytes >= 0),
  largura       int,
  altura        int,
  is_pdf        boolean     not null default false,
  storage_key   text        not null,
  thumb_key     text,
  criado_por    uuid        not null references public.profiles(id) on delete restrict,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create index if not exists ix_revisao_arquivos_revisao on public.revisao_arquivos (revisao_id);
create index if not exists ix_revisao_arquivos_projeto on public.revisao_arquivos (projeto_id);
create index if not exists ix_revisao_arquivos_tenant  on public.revisao_arquivos (tenant_id);

-- ===================== MOODBOARD_SECOES =====================
create table if not exists public.moodboard_secoes (
  id          uuid        primary key,                                -- gerado no cliente
  projeto_id  uuid        not null references public.projetos(id) on delete cascade,
  tenant_id   uuid        not null references public.profiles(id) on delete restrict,
  nome        text        not null,
  ordem       int         not null default 0,
  created_by  uuid        not null references public.profiles(id) on delete restrict,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create index if not exists ix_moodboard_secoes_projeto on public.moodboard_secoes (projeto_id, ordem);

drop trigger if exists trg_moodboard_secoes_updated_at on public.moodboard_secoes;
create trigger trg_moodboard_secoes_updated_at
  before update on public.moodboard_secoes
  for each row execute function public.set_updated_at();

-- ===================== MOODBOARD_ITENS (imagem de referência; espelha anexos) =====================
create table if not exists public.moodboard_itens (
  id            uuid        primary key,                              -- gerado no cliente
  projeto_id    uuid        not null references public.projetos(id) on delete cascade,
  tenant_id     uuid        not null references public.profiles(id) on delete restrict,
  secao_id      uuid        references public.moodboard_secoes(id) on delete set null,  -- agrupamento opcional
  legenda       text,
  nome_arquivo  text        not null,
  content_type  text        not null,
  tamanho_bytes bigint      not null check (tamanho_bytes >= 0),
  largura       int,
  altura        int,
  storage_key   text        not null,
  thumb_key     text,
  ordem         int         not null default 0,
  seq_humano    bigint,                                              -- trigger (0037)
  criado_por    uuid        not null references public.profiles(id) on delete restrict,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create unique index if not exists uq_moodboard_itens_tenant_seq on public.moodboard_itens (tenant_id, seq_humano);
create index        if not exists ix_moodboard_itens_projeto on public.moodboard_itens (projeto_id, ordem);
create index        if not exists ix_moodboard_itens_tenant  on public.moodboard_itens (tenant_id);
create index        if not exists ix_moodboard_itens_secao   on public.moodboard_itens (secao_id);

drop trigger if exists trg_moodboard_itens_updated_at on public.moodboard_itens;
create trigger trg_moodboard_itens_updated_at
  before update on public.moodboard_itens
  for each row execute function public.set_updated_at();
