-- 0091_billing_stripe_v2.sql  (Billing v2 — Stripe como fonte da licença: multi-plano + histórico)
--
-- CONTEXTO: o controle de plano deixa de depender de concessão manual (0090 vira só cortesia/trial).
-- O caminho normal é o arquiteto ASSINAR no Stripe; o webhook reflete o estado e ESTE arquivo adiciona:
--   (a) multi-plano: cada plano pago aponta p/ um Stripe Price (planos.stripe_price_id);
--   (b) ledger de pagamentos (cobranca_pagamentos) p/ "último pagamento / valor / data";
--   (c) histórico de planos (tenant_plano_historico) p/ "épocas que foi pro/free".
-- Segue o padrão dos outros arquivos (owner postgres; revoke public/anon; grant a authenticated e/ou
-- cria_app — o webhook roda como cria_app, fora do contexto authenticated).
--
-- Aplicar como postgres (SQL Editor / db push), DEPOIS do 0090. A conexão cria_app é não-owner.

-- =====================================================================================
-- (1) Multi-plano: cada plano pago aponta p/ um Stripe Price. Assinável = ativo AND price não nulo.
-- =====================================================================================
alter table public.planos
  add column if not exists stripe_price_id text;
create unique index if not exists uq_planos_stripe_price
  on public.planos (stripe_price_id) where stripe_price_id is not null;

-- =====================================================================================
-- (2) Ledger de pagamentos. Idempotente por invoice (o webhook pode reentregar o mesmo evento).
--     Default-deny: RLS on, sem grant a cria_app e sem policy — só as funções definer leem/escrevem.
-- =====================================================================================
create table if not exists public.cobranca_pagamentos (
  id                uuid        primary key default gen_random_uuid(),
  tenant_id         uuid        not null references public.profiles(id) on delete cascade,
  stripe_invoice_id text        unique,
  valor_cents       bigint      not null,
  moeda             text        not null default 'brl',
  plano_codigo      text,                                  -- snapshot do plano no momento do pagamento
  pago_em           timestamptz not null,
  created_at        timestamptz not null default now()
);
create index if not exists ix_cobranca_pagamentos_tenant
  on public.cobranca_pagamentos (tenant_id, pago_em desc);
alter table public.cobranca_pagamentos enable row level security;

-- =====================================================================================
-- (3) Histórico de planos ("épocas pro/free"). Uma linha por período; fim null = vigente.
--     Default-deny (só funções definer). motivo: 'checkout'|'active'|'past_due'|'canceled'|'unpaid'|
--     'admin_cortesia'|'admin_renovou'|'admin_revogou'|...
-- =====================================================================================
create table if not exists public.tenant_plano_historico (
  id           uuid        primary key default gen_random_uuid(),
  tenant_id    uuid        not null references public.profiles(id) on delete cascade,
  plano_codigo text        not null,
  origem       text        not null default 'stripe',     -- 'stripe' | 'manual'
  inicio       timestamptz not null default now(),
  fim          timestamptz,                                -- null = período vigente
  motivo       text
);
create index if not exists ix_tenant_plano_historico_tenant
  on public.tenant_plano_historico (tenant_id, inicio desc);
alter table public.tenant_plano_historico enable row level security;

-- =====================================================================================
-- (4) registrar_transicao_plano: fecha o período vigente e abre um novo SE o plano mudou (idempotente).
--     Chamada pelo webhook (via cobranca_aplicar, role cria_app) e pelas ações admin (authenticated).
-- =====================================================================================
create or replace function public.registrar_transicao_plano(
  p_tenant uuid, p_plano text, p_origem text, p_motivo text
) returns void language plpgsql security definer set search_path = '' as $$
declare v_atual text;
begin
  select h.plano_codigo into v_atual
    from public.tenant_plano_historico h
    where h.tenant_id = p_tenant and h.fim is null
    order by h.inicio desc limit 1;

  if v_atual is distinct from p_plano then
    update public.tenant_plano_historico
       set fim = now()
     where tenant_id = p_tenant and fim is null;
    insert into public.tenant_plano_historico (tenant_id, plano_codigo, origem, inicio, motivo)
    values (p_tenant, p_plano, coalesce(p_origem, 'stripe'), now(), p_motivo);
  end if;
end; $$;
alter function public.registrar_transicao_plano(uuid, text, text, text) owner to postgres;
revoke all on function public.registrar_transicao_plano(uuid, text, text, text) from public, anon;
grant execute on function public.registrar_transicao_plano(uuid, text, text, text)
  to authenticated, cria_app;

-- =====================================================================================
-- (5a) plano_por_price: resolve o plano (codigo) a partir do Stripe Price. Definer porque o webhook
--      roda como cria_app, que NÃO tem grant em planos (RLS default-deny). null se não casar.
-- =====================================================================================
create or replace function public.plano_por_price(p_price text)
returns text language sql stable security definer set search_path = '' as $$
  select codigo from public.planos where stripe_price_id = p_price and ativo limit 1;
$$;
alter function public.plano_por_price(text) owner to postgres;
revoke all on function public.plano_por_price(text) from public, anon;
grant execute on function public.plano_por_price(text) to authenticated, cria_app;

-- planos_assinaveis: catálogo visível ao ARQUITETO p/ assinar (só ativos com Stripe Price). Sem gate
-- de admin (qualquer logado escolhe um plano), mas planos é RLS default-deny → precisa ser definer.
create or replace function public.planos_assinaveis()
returns table (codigo text, nome text, limites jsonb, flags jsonb, preco_mensal numeric, ordem int)
language sql stable security definer set search_path = '' as $$
  select p.codigo, p.nome, p.limites, p.flags, p.preco_mensal, p.ordem
  from public.planos p
  where p.ativo and p.stripe_price_id is not null
  order by p.ordem, p.codigo;
$$;
alter function public.planos_assinaveis() owner to postgres;
revoke all on function public.planos_assinaveis() from public, anon;
grant execute on function public.planos_assinaveis() to authenticated;

-- =====================================================================================
-- (5b) cobranca_registrar_pagamento: grava 1 fatura paga (idempotente por invoice). Caminho do
--      webhook (cria_app): resolve o tenant pelo customer quando o metadata não traz tenant_id.
-- =====================================================================================
create or replace function public.cobranca_registrar_pagamento(
  p_tenant uuid, p_customer text, p_invoice text, p_cents bigint,
  p_moeda text, p_plano text, p_pago_em timestamptz
) returns void language plpgsql security definer set search_path = '' as $$
declare v_tenant uuid;
begin
  v_tenant := coalesce(
    p_tenant,
    (select tenant_id from public.tenant_cobranca where stripe_customer_id = p_customer)
  );
  if v_tenant is null then
    return;                                   -- sem tenant resolvível → ignora (não dá erro no webhook)
  end if;
  insert into public.cobranca_pagamentos
    (tenant_id, stripe_invoice_id, valor_cents, moeda, plano_codigo, pago_em)
  values
    (v_tenant, p_invoice, p_cents, coalesce(p_moeda, 'brl'), p_plano, coalesce(p_pago_em, now()))
  on conflict (stripe_invoice_id) do nothing;
end; $$;
alter function public.cobranca_registrar_pagamento(uuid, text, text, bigint, text, text, timestamptz)
  owner to postgres;
revoke all on function public.cobranca_registrar_pagamento(uuid, text, text, bigint, text, text, timestamptz)
  from public, anon;
grant execute on function public.cobranca_registrar_pagamento(uuid, text, text, bigint, text, text, timestamptz)
  to authenticated, cria_app;

-- =====================================================================================
-- (6) cobranca_aplicar v3: além de espelhar o estado (0090: origem='stripe', expira_em=null), REGISTRA
--     a transição de plano no histórico. p_status vira o "motivo" da época.
-- =====================================================================================
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
    insert into public.tenant_assinaturas (tenant_id, plano_codigo, origem, expira_em)
    values (p_tenant, p_plano, 'stripe', null)
    on conflict (tenant_id) do update set
      plano_codigo = excluded.plano_codigo,
      origem       = 'stripe',
      expira_em    = null;
    perform public.registrar_transicao_plano(p_tenant, p_plano, 'stripe', p_status);
  end if;
end; $$;
alter function public.cobranca_aplicar(uuid, text, text, text, timestamptz, text) owner to postgres;
revoke all on function public.cobranca_aplicar(uuid, text, text, text, timestamptz, text)
  from public, anon;
grant execute on function public.cobranca_aplicar(uuid, text, text, text, timestamptz, text)
  to authenticated, cria_app;

-- =====================================================================================
-- (7) admin_listar_tenants v2: + assinante_desde, último pagamento (data/valor); e ESCOPA a clientes
--     do SaaS = arquitetos (exclui cliente-puro do portal: só aparece como papel='cliente' e não é
--     dono de obra/projeto — mesma regra do RoleShell clienteEhPuro).
--     Ganhou colunas novas no retorno → DROP antes (create or replace não muda o tipo de retorno).
-- =====================================================================================
drop function if exists public.admin_listar_tenants();
create or replace function public.admin_listar_tenants()
returns table (
  tenant_id          uuid,
  email              text,
  nome               text,
  nome_escritorio    text,
  plano_codigo       text,
  plano_nome         text,
  origem             text,
  expira_em          timestamptz,
  observacao         text,
  cobranca_status    text,
  current_period_end timestamptz,
  assinante_desde    timestamptz,   -- 1ª época com plano != free (do histórico)
  ultimo_pagamento_em    timestamptz,
  ultimo_pagamento_cents bigint,
  obras_ativas       bigint,
  armazenamento_bytes bigint,
  created_at         timestamptz
)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  return query
    select
      p.id,
      p.email::text,
      p.nome,
      b.nome_escritorio,
      ef.codigo,
      ef.nome,
      a.origem,
      a.expira_em,
      a.observacao,
      c.status,
      c.current_period_end,
      (select min(h.inicio) from public.tenant_plano_historico h
        where h.tenant_id = p.id and h.plano_codigo <> 'free'),
      pg.pago_em,
      pg.valor_cents,
      (select count(*) from public.obras o where o.tenant_id = p.id and o.status = 'ativa'),
      public.consumo_armazenamento_bytes(p.id),
      p.created_at
    from public.profiles p
    left join public.tenant_assinaturas a on a.tenant_id = p.id
    left join public.tenant_branding    b on b.tenant_id = p.id
    left join public.tenant_cobranca    c on c.tenant_id = p.id
    left join lateral (
      select pl.codigo, pl.nome
      from public.planos pl
      where pl.codigo = coalesce(
        (select aa.plano_codigo from public.tenant_assinaturas aa
          where aa.tenant_id = p.id
            and (aa.expira_em is null or aa.expira_em > now())),
        'free')
    ) ef on true
    left join lateral (
      select pgi.pago_em, pgi.valor_cents
      from public.cobranca_pagamentos pgi
      where pgi.tenant_id = p.id
      order by pgi.pago_em desc limit 1
    ) pg on true
    where (
        not exists (select 1 from public.obra_membros om
                     where om.profile_id = p.id and om.papel = 'cliente')
        and not exists (select 1 from public.projeto_membros pm
                         where pm.profile_id = p.id and pm.papel = 'cliente')
      )
      or exists (select 1 from public.obras o2 where o2.tenant_id = p.id)
      or exists (select 1 from public.projetos pr where pr.tenant_id = p.id)
    order by p.created_at desc;
end; $$;
alter function public.admin_listar_tenants() owner to postgres;
revoke all on function public.admin_listar_tenants() from public, anon;
grant execute on function public.admin_listar_tenants() to authenticated;

-- =====================================================================================
-- (8) Detalhe do cliente: timeline de planos + pagamentos. Ambas gateadas por is_platform_admin().
-- =====================================================================================
create or replace function public.admin_planos_historico(p_tenant uuid)
returns table (plano_codigo text, origem text, inicio timestamptz, fim timestamptz, motivo text)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  return query
    select h.plano_codigo, h.origem, h.inicio, h.fim, h.motivo
    from public.tenant_plano_historico h
    where h.tenant_id = p_tenant
    order by h.inicio desc;
end; $$;
alter function public.admin_planos_historico(uuid) owner to postgres;
revoke all on function public.admin_planos_historico(uuid) from public, anon;
grant execute on function public.admin_planos_historico(uuid) to authenticated;

create or replace function public.admin_pagamentos(p_tenant uuid)
returns table (valor_cents bigint, moeda text, plano_codigo text, pago_em timestamptz)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  return query
    select g.valor_cents, g.moeda, g.plano_codigo, g.pago_em
    from public.cobranca_pagamentos g
    where g.tenant_id = p_tenant
    order by g.pago_em desc;
end; $$;
alter function public.admin_pagamentos(uuid) owner to postgres;
revoke all on function public.admin_pagamentos(uuid) from public, anon;
grant execute on function public.admin_pagamentos(uuid) to authenticated;

-- (8b) Churn: nº de tenants que caíram de um plano pago p/ free nos últimos p_dias (transição
--      registrada no histórico: a época 'free' começou exatamente quando a paga terminou, fim=inicio).
create or replace function public.admin_churn(p_dias int)
returns bigint language plpgsql stable security definer set search_path = '' as $$
declare n bigint;
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  select count(distinct r.tenant_id) into n
  from public.tenant_plano_historico r
  where r.plano_codigo = 'free'
    and r.inicio >= now() - make_interval(days => p_dias)
    and exists (
      select 1 from public.tenant_plano_historico r2
      where r2.tenant_id = r.tenant_id and r2.plano_codigo <> 'free' and r2.fim = r.inicio
    );
  return coalesce(n, 0);
end; $$;
alter function public.admin_churn(int) owner to postgres;
revoke all on function public.admin_churn(int) from public, anon;
grant execute on function public.admin_churn(int) to authenticated;

-- =====================================================================================
-- (9) Concessão manual (0090) passa a REGISTRAR no histórico (origem='manual'). Mantém a assinatura
--     como cortesia/trial; o caminho normal é o Stripe.
-- =====================================================================================
create or replace function public.admin_definir_plano(
  p_tenant uuid, p_plano text, p_meses int, p_obs text
) returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  if not exists (select 1 from public.planos where codigo = p_plano) then
    raise exception 'plano inexistente: %', p_plano using errcode = '23503';
  end if;
  if p_meses is not null and p_meses <= 0 then
    raise exception 'meses deve ser positivo' using errcode = '22023';
  end if;
  insert into public.tenant_assinaturas
    (tenant_id, plano_codigo, origem, expira_em, concedido_por, observacao)
  values (
    p_tenant, p_plano, 'manual',
    case when p_meses is null then null else now() + make_interval(months => p_meses) end,
    (select auth.uid()), p_obs
  )
  on conflict (tenant_id) do update set
    plano_codigo  = excluded.plano_codigo,
    origem        = 'manual',
    expira_em     = excluded.expira_em,
    concedido_por = excluded.concedido_por,
    observacao    = excluded.observacao;
  perform public.registrar_transicao_plano(p_tenant, p_plano, 'manual', 'admin_cortesia');
end; $$;
alter function public.admin_definir_plano(uuid, text, int, text) owner to postgres;
revoke all on function public.admin_definir_plano(uuid, text, int, text) from public, anon;
grant execute on function public.admin_definir_plano(uuid, text, int, text) to authenticated;

create or replace function public.admin_renovar_plano(p_tenant uuid, p_meses int)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  if p_meses is null or p_meses <= 0 then
    raise exception 'meses deve ser positivo' using errcode = '22023';
  end if;
  update public.tenant_assinaturas
     set expira_em     = greatest(coalesce(expira_em, now()), now()) + make_interval(months => p_meses),
         origem        = 'manual',
         concedido_por = (select auth.uid())
   where tenant_id = p_tenant;
  if not found then
    raise exception 'tenant sem assinatura para renovar (conceda um plano antes)' using errcode = 'P0002';
  end if;
  perform public.registrar_transicao_plano(
    p_tenant,
    (select plano_codigo from public.tenant_assinaturas where tenant_id = p_tenant),
    'manual', 'admin_renovou');
end; $$;
alter function public.admin_renovar_plano(uuid, int) owner to postgres;
revoke all on function public.admin_renovar_plano(uuid, int) from public, anon;
grant execute on function public.admin_renovar_plano(uuid, int) to authenticated;

create or replace function public.admin_revogar_plano(p_tenant uuid)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  delete from public.tenant_assinaturas where tenant_id = p_tenant;
  perform public.registrar_transicao_plano(p_tenant, 'free', 'manual', 'admin_revogou');
end; $$;
alter function public.admin_revogar_plano(uuid) owner to postgres;
revoke all on function public.admin_revogar_plano(uuid) from public, anon;
grant execute on function public.admin_revogar_plano(uuid) to authenticated;

-- =====================================================================================
-- (10) Catálogo de planos no painel agora expõe/edita o stripe_price_id (multi-plano). Recria
--      admin_listar_planos (nova coluna no retorno) e admin_upsert_plano (novo parâmetro) — exige
--      DROP (create or replace não muda assinatura/retorno).
-- =====================================================================================
drop function if exists public.admin_listar_planos();
create or replace function public.admin_listar_planos()
returns table (
  codigo text, nome text, limites jsonb, flags jsonb,
  preco_mensal numeric, ativo boolean, ordem int, stripe_price_id text
)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  return query
    select p.codigo, p.nome, p.limites, p.flags, p.preco_mensal, p.ativo, p.ordem, p.stripe_price_id
    from public.planos p
    order by p.ordem, p.codigo;
end; $$;
alter function public.admin_listar_planos() owner to postgres;
revoke all on function public.admin_listar_planos() from public, anon;
grant execute on function public.admin_listar_planos() to authenticated;

drop function if exists public.admin_upsert_plano(text, text, jsonb, jsonb, numeric, boolean, int);
create or replace function public.admin_upsert_plano(
  p_codigo text, p_nome text, p_limites jsonb, p_flags jsonb,
  p_preco numeric, p_ativo boolean, p_ordem int, p_stripe_price text
) returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  insert into public.planos
    (codigo, nome, limites, flags, preco_mensal, ativo, ordem, stripe_price_id)
  values (p_codigo, p_nome, coalesce(p_limites, '{}'::jsonb), coalesce(p_flags, '{}'::jsonb),
          p_preco, coalesce(p_ativo, true), coalesce(p_ordem, 0), nullif(btrim(p_stripe_price), ''))
  on conflict (codigo) do update set
    nome            = excluded.nome,
    limites         = excluded.limites,
    flags           = excluded.flags,
    preco_mensal    = excluded.preco_mensal,
    ativo           = excluded.ativo,
    ordem           = excluded.ordem,
    stripe_price_id = excluded.stripe_price_id;
end; $$;
alter function public.admin_upsert_plano(text, text, jsonb, jsonb, numeric, boolean, int, text)
  owner to postgres;
revoke all on function public.admin_upsert_plano(text, text, jsonb, jsonb, numeric, boolean, int, text)
  from public, anon;
grant execute on function public.admin_upsert_plano(text, text, jsonb, jsonb, numeric, boolean, int, text)
  to authenticated;
