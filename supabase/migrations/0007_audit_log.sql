-- 0007_audit_log.sql  (Fase 1)
-- Audit log CORE, append-only, 2 camadas. Owner postgres (NÃO cria_app).
-- Camada de sistema (cru/factual) + camada de exibição (snapshot CONGELADO do rótulo).

create table public.audit_log (
  id            uuid        primary key default gen_random_uuid(),
  -- camada de sistema (cru, imutável):
  tenant_id     uuid        not null,
  actor_id      uuid,                                  -- profiles.id do ator (null = sistema)
  obra_id       uuid,                                  -- p/ RLS por obra (null = evento sem obra)
  action        text        not null,                  -- ex.: 'obra.arquivada'
  entity_type   text        not null,                  -- ex.: 'obra'
  entity_id     uuid        not null,
  changed       jsonb,                                 -- {"status":{"de":"ativa","para":"arquivada"}}
  -- camada de exibição (snapshot no momento do evento — NUNCA re-hidratar via JOIN ao vivo):
  entity_label  text        not null,                  -- 'Reforma Apto 302'
  entity_seq    bigint,                                -- 42 (o #seq_humano; NUNCA o uuid na UI)
  actor_label   text,                                  -- nome do ator naquele instante
  created_at    timestamptz not null default now()
);

create index ix_audit_tenant_created on public.audit_log (tenant_id, created_at desc);
create index ix_audit_obra           on public.audit_log (obra_id);
create index ix_audit_entity         on public.audit_log (entity_type, entity_id);
