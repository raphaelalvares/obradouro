-- 0050_branding.sql  (Fase 7 — personalização: nome do escritório + logo)
-- Marca POR TENANT (o arquiteto). 1 linha por arquiteto. Usada no PDF do checklist (Fase 7) e em
-- relatórios futuros. O BYTE do logo vive no storage (módulo da Fase 4); aqui guardamos só a CHAVE
-- opaca + o mime. O gate de plano (flag 'logo') é aplicado no BACKEND (service) — esta tabela não
-- conhece plano. Sem seq humano (config de conta, não entidade de obra) e SEM audit (escopo do
-- cria_audit_log é obra/projeto; marca é nível-conta).

create table if not exists public.tenant_branding (
  tenant_id        uuid        primary key references public.profiles(id) on delete cascade,
  nome_escritorio  text,
  logo_key         text,       -- chave opaca no storage (NULL = sem logo)
  logo_mime        text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
drop trigger if exists trg_tenant_branding_updated_at on public.tenant_branding;
create trigger trg_tenant_branding_updated_at
  before update on public.tenant_branding for each row execute function public.set_updated_at();

grant select, insert, update, delete on public.tenant_branding to cria_app;
alter table public.tenant_branding enable row level security;

-- Self-service: o arquiteto só vê/edita a PRÓPRIA marca (tenant_id = ele mesmo).
drop policy if exists tenant_branding_select on public.tenant_branding;
create policy tenant_branding_select on public.tenant_branding
  for select to authenticated
  using ( tenant_id = (select auth.uid()) );

drop policy if exists tenant_branding_insert on public.tenant_branding;
create policy tenant_branding_insert on public.tenant_branding
  for insert to authenticated
  with check ( tenant_id = (select auth.uid()) );

drop policy if exists tenant_branding_update on public.tenant_branding;
create policy tenant_branding_update on public.tenant_branding
  for update to authenticated
  using      ( tenant_id = (select auth.uid()) )
  with check ( tenant_id = (select auth.uid()) );

drop policy if exists tenant_branding_delete on public.tenant_branding;
create policy tenant_branding_delete on public.tenant_branding
  for delete to authenticated
  using ( tenant_id = (select auth.uid()) );

-- Leitura da marca de QUALQUER tenant — o PDF do checklist pode ser gerado por cliente/prestador
-- (não-dono da marca; a RLS acima barraria). SECURITY DEFINER (isenção de owner) expondo só os 3
-- campos de marca (nada sensível) e sem efeito colateral. Espelha plano_do_tenant (0020).
create or replace function public.branding_do_tenant(p_tenant uuid)
returns table (nome_escritorio text, logo_key text, logo_mime text)
language sql stable security definer set search_path = '' as $$
  select b.nome_escritorio, b.logo_key, b.logo_mime
  from public.tenant_branding b
  where b.tenant_id = p_tenant;
$$;
alter function public.branding_do_tenant(uuid) owner to postgres;
revoke all on function public.branding_do_tenant(uuid) from public, anon;
grant execute on function public.branding_do_tenant(uuid) to authenticated;
