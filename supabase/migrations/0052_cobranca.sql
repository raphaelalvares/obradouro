-- 0052_cobranca.sql  (Fase 9 — cobrança/Stripe, MÓDULO SEPARADO do controle de plano)
-- Planejamento §5: "controle de plano" (tenant_assinaturas, Fase 2) é uma coisa; "cobrança"
-- (gateway, recorrência, webhooks) é outra — NÃO acoplar. Aqui ficam só os FATOS de billing do
-- Stripe. Quem decide "qual plano" continua sendo tenant_assinaturas; o webhook traduz o estado da
-- assinatura Stripe → plano_codigo via a função SECURITY DEFINER abaixo (o webhook não tem auth.uid()).

create table if not exists public.tenant_cobranca (
  tenant_id              uuid        primary key references public.profiles(id) on delete cascade,
  stripe_customer_id     text        unique,
  stripe_subscription_id text,
  status                 text,        -- status da subscription no Stripe (active/past_due/canceled…)
  current_period_end     timestamptz, -- fim do período pago atual (renovação)
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);
create index if not exists ix_tenant_cobranca_customer on public.tenant_cobranca (stripe_customer_id);
drop trigger if exists trg_tenant_cobranca_updated_at on public.tenant_cobranca;
create trigger trg_tenant_cobranca_updated_at
  before update on public.tenant_cobranca for each row execute function public.set_updated_at();

grant select, insert, update, delete on public.tenant_cobranca to cria_app;
alter table public.tenant_cobranca enable row level security;

-- Leitura self (a UI mostra status/renovação). ESCRITAS só pelas funções SECURITY DEFINER abaixo
-- (o checkout autenticado e o webhook sem auth) — nenhuma policy de escrita para authenticated.
drop policy if exists tenant_cobranca_select on public.tenant_cobranca;
create policy tenant_cobranca_select on public.tenant_cobranca
  for select to authenticated using ( tenant_id = (select auth.uid()) );

-- Guarda o customer do Stripe ao criar o checkout (caminho autenticado; recebe o tenant por param).
create or replace function public.cobranca_set_customer(p_tenant uuid, p_customer text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  insert into public.tenant_cobranca (tenant_id, stripe_customer_id)
  values (p_tenant, p_customer)
  on conflict (tenant_id) do update set stripe_customer_id = excluded.stripe_customer_id;
end; $$;
alter function public.cobranca_set_customer(uuid, text) owner to postgres;
revoke all on function public.cobranca_set_customer(uuid, text) from public, anon;
grant execute on function public.cobranca_set_customer(uuid, text) to authenticated, cria_app;

-- Aplica o estado da assinatura Stripe (caminho do WEBHOOK, sem auth.uid()): atualiza os fatos de
-- billing E, quando p_plano vem preenchido, espelha no controle de plano (tenant_assinaturas).
-- p_plano ∈ planos.codigo ('pro'/'free'); o webhook traduz status→plano. Grant a cria_app pois o
-- webhook roda fora do contexto authenticated.
create or replace function public.cobranca_aplicar(
  p_tenant uuid, p_customer text, p_subscription text,
  p_status text, p_period_end timestamptz, p_plano text
) returns void language plpgsql security definer set search_path = '' as $$
begin
  insert into public.tenant_cobranca
    (tenant_id, stripe_customer_id, stripe_subscription_id, status, current_period_end)
  values (p_tenant, p_customer, p_subscription, p_status, p_period_end)
  on conflict (tenant_id) do update set
    stripe_customer_id     = coalesce(excluded.stripe_customer_id,
                                      public.tenant_cobranca.stripe_customer_id),
    stripe_subscription_id = excluded.stripe_subscription_id,
    status                 = excluded.status,
    current_period_end     = excluded.current_period_end;

  if p_plano is not null then
    insert into public.tenant_assinaturas (tenant_id, plano_codigo)
    values (p_tenant, p_plano)
    on conflict (tenant_id) do update set plano_codigo = excluded.plano_codigo;
  end if;
end; $$;
alter function public.cobranca_aplicar(uuid, text, text, text, timestamptz, text) owner to postgres;
revoke all on function public.cobranca_aplicar(uuid, text, text, text, timestamptz, text)
  from public, anon;
grant execute on function public.cobranca_aplicar(uuid, text, text, text, timestamptz, text)
  to authenticated, cria_app;
