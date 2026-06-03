-- 0028_anexos_tables.sql  (Fase 4 — Storage + Anexos: tabela)
-- Anexo = midia INFORMAL (foto/observacao da execucao). Entidade INDEPENDENTE (decisao travada):
-- NAO e a revisao versionada do Modulo de Projeto (essa tem ciclo aprovacao, vem na Fase 5).
-- FK polimorfica resolvida DESNORMALIZANDO obra_id (ponto "h" do review): o anexo aponta para
-- 'etapa' OU 'checklist_item' via (parent_type, parent_id) SEM FK (polimorfico), mas carrega
-- obra_id/tenant_id proprios -> RLS por obra_id sem JOIN e contabilizacao de consumo por tenant.
-- Dual-ID: id = UUID gerado no cliente (offline) + seq_humano por tenant (trigger 0029).
-- Os BYTES vivem no backend de storage (Drive/disco/etc., atras do modulo app.services.storage);
-- aqui guardamos so o METADADO + as CHAVES opacas (storage_key/thumb_key) para recuperar/expurgar.

create table if not exists public.anexos (
  id            uuid        primary key,                              -- gerado no cliente (offline)
  obra_id       uuid        not null references public.obras(id)     on delete cascade,
  tenant_id     uuid        not null references public.profiles(id)  on delete restrict,

  -- alvo polimorfico (2 niveis na UI: anexo de etapa OU de item). SEM FK: a coerencia
  -- (parent pertence a obra_id) e imposta pelo guard 0031; a limpeza ao apagar o pai e o 0032.
  parent_type   text        not null check (parent_type in ('etapa', 'checklist_item')),
  parent_id     uuid        not null,

  nome_arquivo  text        not null,                                 -- nome original (higienizado)
  content_type  text        not null,                                 -- mime do 'full' ARMAZENADO
  tamanho_bytes bigint      not null check (tamanho_bytes >= 0),      -- tamanho do 'full' (p/ quota)
  largura       int,                                                  -- dimensoes do 'full' (px)
  altura        int,

  storage_key   text        not null,                                 -- chave opaca do 'full' no backend
  thumb_key     text,                                                 -- chave opaca da miniatura (nullable)

  criado_por    uuid        not null references public.profiles(id)  on delete restrict,
  seq_humano    bigint,                                              -- preenchido pelo trigger (0029)
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

-- rotulo humano unico por tenant (espelha uq_obras_tenant_seq / uq_etapas_tenant_seq)
create unique index if not exists uq_anexos_tenant_seq on public.anexos (tenant_id, seq_humano);
-- listagem por alvo (galeria de um item/etapa), ja ordenada por chegada
create index        if not exists ix_anexos_parent     on public.anexos (parent_type, parent_id, created_at);
-- RLS por obra + limpeza por obra
create index        if not exists ix_anexos_obra       on public.anexos (obra_id);
-- soma de consumo por tenant (quota de armazenamento, 0033) sem varrer por obra
create index        if not exists ix_anexos_tenant     on public.anexos (tenant_id);

drop trigger if exists trg_anexos_updated_at on public.anexos;
create trigger trg_anexos_updated_at
  before update on public.anexos
  for each row execute function public.set_updated_at();
