-- 0107_quota_portal_logo.sql  (monetização — FECHA O FURO da cota de armazenamento)
-- Achado: a cota (0042) só somava anexos + moodboard_itens + revisao_arquivos. A mídia do PORTAL
-- (projeto_etapa_anexos: material da etapa + renders 3D via ambiente_id + anexos do manual via
-- manual_item_id — 0099/0100/0101) e o LOGO do escritório (tenant_branding — 0050) gravam bytes mas
-- ficavam FORA do consumo → dava p/ encher GBs sem contar (e vender "X GB" mentindo). Aqui:
--   (1) tenant_branding ganha tamanho_bytes (o service passa a gravar; ver branding.py);
--   (2) consumo_armazenamento_bytes passa a somar projeto_etapa_anexos + o logo;
--   (3) projeto_etapa_anexos ganha o trigger de quota (o guard genérico 0042). O backend
--       (pipeline.py) JÁ traduz o P0001 'limite_armazenamento' → 403+upsell — só faltava disparar.
-- NÃO gateamos o logo por trigger (é 1 arquivo pequeno, já gated pela flag 'logo', e o upsert
-- reprocessaria a linha antiga → double-count): ele CONTA no painel, mas não bloqueia.
-- export_jobs (0051) segue FORA da cota de propósito (artefato gerado/efêmero, não mídia do cliente).
-- Depende de 0042 (guard genérico + consumo), 0050 (tenant_branding), 0099 (projeto_etapa_anexos).
-- Aplicar como postgres, após 0106. Idempotente.

begin;

-- ===================== (1) logo passa a carregar o tamanho gravado =====================
alter table public.tenant_branding
  add column if not exists tamanho_bytes bigint
    check (tamanho_bytes is null or tamanho_bytes >= 0);
-- Logos JÁ existentes ficam com tamanho_bytes NULL (contam 0) até o próximo re-upload — desvio
-- irrelevante (1 PNG normalizado por tenant) e some sozinho.

-- ===================== (2) consumo unificado agora inclui portal + logo =====================
-- Mesma função de 0042, com dois ramos novos. sum() ignora NULL, mas coalesce deixa explícito que
-- LINK (projeto_etapa_anexos.tipo='link') e logo ausente contam 0. Só chamada por funções definer.
create or replace function public.consumo_armazenamento_bytes(p_tenant uuid)
returns bigint
language plpgsql stable security definer set search_path = '' as $$
declare v bigint;
begin
  select coalesce(sum(t.b), 0) into v from (
    select a.tamanho_bytes                as b from public.anexos              a   where a.tenant_id   = p_tenant
    union all
    select m.tamanho_bytes                     from public.moodboard_itens    m   where m.tenant_id   = p_tenant
    union all
    select ra.tamanho_bytes                    from public.revisao_arquivos   ra  where ra.tenant_id  = p_tenant
    union all
    select coalesce(pea.tamanho_bytes, 0)      from public.projeto_etapa_anexos pea where pea.tenant_id = p_tenant
    union all
    select coalesce(tb.tamanho_bytes, 0)       from public.tenant_branding    tb  where tb.tenant_id  = p_tenant
  ) t;
  return v;
end;
$$;
alter function public.consumo_armazenamento_bytes(uuid) owner to postgres;
revoke all on function public.consumo_armazenamento_bytes(uuid) from public, anon, authenticated;

-- ===================== (3) trava de quota no upload de mídia do portal =====================
-- Reusa o guard genérico (usa new.tenant_id + new.tamanho_bytes). Nome 'quota' > 'guard' → o
-- projeto_etapa_anexos_guard (coerência/papel) roda ANTES; a quota depois (convenção g < q do 0042).
-- LINK (tamanho_bytes NULL) nunca bloqueia: v_usado + NULL = NULL → não dispara. Só INSERT (o guard
-- já proíbe UPDATE; DELETE precisa liberar espaço).
drop trigger if exists trg_projeto_etapa_anexos_quota on public.projeto_etapa_anexos;
create trigger trg_projeto_etapa_anexos_quota
  before insert on public.projeto_etapa_anexos
  for each row execute function public.enforce_quota_armazenamento();

commit;
