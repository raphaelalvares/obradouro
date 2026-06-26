-- 0090_admin_plataforma.sql  (Painel de admin da plataforma — dono do SaaS)
--
-- CONTEXTO: o CRIA é estruturalmente single-tenant (tenant_id = auth.uid()); toda leitura passa por
-- RLS escopada ao próprio usuário. NÃO existe "dono da plataforma". Este painel é um PLANO DE
-- AUTORIZAÇÃO NOVO que, deliberadamente, fura a RLS via SECURITY DEFINER — SEMPRE depois de checar
-- is_platform_admin(auth.uid()). Segue o padrão de plano_do_tenant/branding_do_tenant/cobranca_aplicar
-- (owner postgres; revoke de public/anon; grant execute a authenticated).
--
-- Aplicar como postgres (SQL Editor / db push), DEPOIS do 0089. A conexão cria_app é não-owner.

-- =====================================================================================
-- (1) Quem é admin da plataforma. Default-deny: RLS ligada, SEM grant a cria_app e SEM policy —
--     só as funções SECURITY DEFINER abaixo leem esta tabela.
-- =====================================================================================
create table if not exists public.platform_admins (
  profile_id uuid        primary key references public.profiles(id) on delete cascade,
  created_at timestamptz not null default now()
);
alter table public.platform_admins enable row level security;

-- Seed do dono. Resolve email→id no momento do apply (idempotente). Se o profile ainda não existir
-- (você não criou conta com esse email), o INSERT é no-op — rode o fallback no fim do arquivo após o
-- 1º login.
insert into public.platform_admins (profile_id)
select id from public.profiles where email = 'mecreeps6@gmail.com'
on conflict do nothing;

-- Gate central: o usuário corrente é admin da plataforma? Usado pela API (dependency) e por TODA
-- função admin abaixo (defesa em profundidade).
create or replace function public.is_platform_admin()
returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.platform_admins a where a.profile_id = (select auth.uid())
  );
$$;
alter function public.is_platform_admin() owner to postgres;
revoke all on function public.is_platform_admin() from public, anon;
grant execute on function public.is_platform_admin() to authenticated;

-- =====================================================================================
-- (2) Validade/origem da assinatura (modelo manual + Stripe) + preço mensal no catálogo.
-- =====================================================================================
alter table public.tenant_assinaturas
  add column if not exists origem        text        not null default 'manual',  -- 'manual' | 'stripe'
  add column if not exists expira_em     timestamptz,                            -- null = sem expiração
  add column if not exists concedido_por uuid references public.profiles(id) on delete set null,
  add column if not exists observacao    text;

-- Preço mensal por plano (pra métrica de receita do painel). Seed: free=0, pro=NULL (defina no painel).
alter table public.planos
  add column if not exists preco_mensal numeric(10,2);
update public.planos set preco_mensal = 0 where codigo = 'free' and preco_mensal is null;

-- =====================================================================================
-- (3) plano_do_tenant v3: respeita a VALIDADE. Assinatura com expira_em no passado é ignorada →
--     cai no 'free' (downgrade automático ao expirar, vale em TODO o gating existente). Stripe
--     (origem='stripe', expira_em=null) não é afetado. Preserva o guard pode_ler_tenant (0077).
-- =====================================================================================
create or replace function public.plano_do_tenant(p_tenant uuid)
returns table (codigo text, nome text, limites jsonb, flags jsonb)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.pode_ler_tenant(p_tenant) then
    p_tenant := null;                      -- B1 (0077): não vaza plano alheio (vira 'free')
  end if;
  return query
    select p.codigo, p.nome, p.limites, p.flags
    from public.planos p
    where p.codigo = coalesce(
      (select a.plano_codigo from public.tenant_assinaturas a
        where a.tenant_id = p_tenant
          and (a.expira_em is null or a.expira_em > now())),  -- licença expirada → ignora → 'free'
      'free');
end; $$;
alter function public.plano_do_tenant(uuid) owner to postgres;
revoke all on function public.plano_do_tenant(uuid) from public, anon;
grant execute on function public.plano_do_tenant(uuid) to authenticated;

-- =====================================================================================
-- (4) cobranca_aplicar v2 (caminho do webhook do Stripe): ao espelhar o plano em tenant_assinaturas,
--     marca origem='stripe' e zera expira_em (o Stripe gere o vencimento via current_period_end;
--     assinar via Stripe sobrescreve uma concessão manual anterior). Mantém 1 linha por tenant.
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
  end if;
end; $$;
alter function public.cobranca_aplicar(uuid, text, text, text, timestamptz, text) owner to postgres;
revoke all on function public.cobranca_aplicar(uuid, text, text, text, timestamptz, text)
  from public, anon;
grant execute on function public.cobranca_aplicar(uuid, text, text, text, timestamptz, text)
  to authenticated, cria_app;

-- =====================================================================================
-- (5) Funções do painel admin. TODAS começam pelo gate is_platform_admin() (errcode 42501 =
--     insufficient_privilege). owner postgres; revoke public/anon; grant a authenticated.
-- =====================================================================================

-- (5a) Lista de clientes (tenants) com plano efetivo, origem, validade, cobrança e uso.
create or replace function public.admin_listar_tenants()
returns table (
  tenant_id          uuid,
  email              text,
  nome               text,
  nome_escritorio    text,
  plano_codigo       text,        -- plano EFETIVO (respeita expiração)
  plano_nome         text,
  origem             text,        -- 'manual' | 'stripe' | null (sem assinatura)
  expira_em          timestamptz, -- validade da concessão manual (null = sem expiração)
  observacao         text,
  cobranca_status    text,        -- status da subscription no Stripe (se houver)
  current_period_end timestamptz, -- fim do período pago no Stripe (se houver)
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
      (select count(*) from public.obras o where o.tenant_id = p.id and o.status = 'ativa'),
      public.consumo_armazenamento_bytes(p.id),
      p.created_at
    from public.profiles p
    left join public.tenant_assinaturas a on a.tenant_id = p.id
    left join public.tenant_branding    b on b.tenant_id = p.id
    left join public.tenant_cobranca    c on c.tenant_id = p.id
    -- plano efetivo (mesma regra de plano_do_tenant: assinatura válida senão 'free')
    left join lateral (
      select pl.codigo, pl.nome
      from public.planos pl
      where pl.codigo = coalesce(
        (select aa.plano_codigo from public.tenant_assinaturas aa
          where aa.tenant_id = p.id
            and (aa.expira_em is null or aa.expira_em > now())),
        'free')
    ) ef on true
    order by p.created_at desc;
end; $$;
alter function public.admin_listar_tenants() owner to postgres;
revoke all on function public.admin_listar_tenants() from public, anon;
grant execute on function public.admin_listar_tenants() to authenticated;

-- (5b) Conceder/trocar plano (manual). p_meses null = sem expiração; senão expira_em = now()+N meses.
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
end; $$;
alter function public.admin_definir_plano(uuid, text, int, text) owner to postgres;
revoke all on function public.admin_definir_plano(uuid, text, int, text) from public, anon;
grant execute on function public.admin_definir_plano(uuid, text, int, text) to authenticated;

-- (5c) Renovar +N meses (mantém o plano). Soma à validade vigente (ou a now() se já expirou/null).
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
end; $$;
alter function public.admin_renovar_plano(uuid, int) owner to postgres;
revoke all on function public.admin_renovar_plano(uuid, int) from public, anon;
grant execute on function public.admin_renovar_plano(uuid, int) to authenticated;

-- (5d) Revogar (volta a 'free' imediatamente).
create or replace function public.admin_revogar_plano(p_tenant uuid)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  delete from public.tenant_assinaturas where tenant_id = p_tenant;
end; $$;
alter function public.admin_revogar_plano(uuid) owner to postgres;
revoke all on function public.admin_revogar_plano(uuid) from public, anon;
grant execute on function public.admin_revogar_plano(uuid) to authenticated;

-- (5e) Catálogo de planos (inclui inativos).
create or replace function public.admin_listar_planos()
returns table (
  codigo text, nome text, limites jsonb, flags jsonb,
  preco_mensal numeric, ativo boolean, ordem int
)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  return query
    select p.codigo, p.nome, p.limites, p.flags, p.preco_mensal, p.ativo, p.ordem
    from public.planos p
    order by p.ordem, p.codigo;
end; $$;
alter function public.admin_listar_planos() owner to postgres;
revoke all on function public.admin_listar_planos() from public, anon;
grant execute on function public.admin_listar_planos() to authenticated;

-- (5f) Criar/editar um plano do catálogo.
create or replace function public.admin_upsert_plano(
  p_codigo text, p_nome text, p_limites jsonb, p_flags jsonb,
  p_preco numeric, p_ativo boolean, p_ordem int
) returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  insert into public.planos (codigo, nome, limites, flags, preco_mensal, ativo, ordem)
  values (p_codigo, p_nome, coalesce(p_limites, '{}'::jsonb), coalesce(p_flags, '{}'::jsonb),
          p_preco, coalesce(p_ativo, true), coalesce(p_ordem, 0))
  on conflict (codigo) do update set
    nome         = excluded.nome,
    limites      = excluded.limites,
    flags        = excluded.flags,
    preco_mensal = excluded.preco_mensal,
    ativo        = excluded.ativo,
    ordem        = excluded.ordem;
end; $$;
alter function public.admin_upsert_plano(text, text, jsonb, jsonb, numeric, boolean, int)
  owner to postgres;
revoke all on function public.admin_upsert_plano(text, text, jsonb, jsonb, numeric, boolean, int)
  from public, anon;
grant execute on function public.admin_upsert_plano(text, text, jsonb, jsonb, numeric, boolean, int)
  to authenticated;

-- =====================================================================================
-- FALLBACK (rode só se o seed do (1) não pegou — ex.: conta criada DEPOIS de aplicar a migration):
--   insert into public.platform_admins (profile_id)
--   select id from public.profiles where email = 'mecreeps6@gmail.com'
--   on conflict do nothing;
-- =====================================================================================
