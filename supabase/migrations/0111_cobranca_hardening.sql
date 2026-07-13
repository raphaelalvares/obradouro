-- 0111_cobranca_hardening.sql  (Cobrança — robustez do webhook + jornadas de expiry/win-back/up-sell)
--
-- CONTEXTO: a auditoria da recorrência mensal achou bugs de CORREÇÃO no webhook que corrompem
-- justamente o dado de que as jornadas de aviso dependem (current_period_end), além de faltar a
-- infra para NOTIFICAR sem duplicar. Esta migration dá a base:
--   (1) `ultimo_evento_em` em tenant_cobranca + `cobranca_aplicar` v4 (retorna boolean "aplicou?"):
--       GUARDA DE RECÊNCIA (evento antigo reentregue não regride o estado — o Stripe entrega
--       at-least-once e SEM ordem) + COALESCE (um evento sem status/period_end — ex.: o ramo de
--       checkout — nunca ZERA um valor já conhecido; era o "sem assinatura" após assinar).
--   (2) `cobranca_avisos` + `cobranca_aviso_uma_vez`/`cobranca_aviso_periodico`: dedupe/throttle dos
--       e-mails de billing. Sem isso, acoplar e-mail ao webhook → duplicado a cada re-entrega.
--   (3) `cobranca_winback_candidatos`: lista (cross-tenant, p/ o reaper como cria_app) quem caiu de
--       plano pago → free e SEGUE free — base da jornada de RE-SELL/win-back.
--   (4) `cobranca_contato`/`cobranca_contato_por_customer`: resolve e-mail/nome do arquiteto dentro
--       do webhook (cria_app, sem JWT) p/ montar o destinatário dos avisos.
--
-- Aplicar como postgres (SQL Editor / db push), DEPOIS do 0110 e ANTES do deploy do backend (o webhook
-- e o reaper de cobrança chamam estas funções). A conexão cria_app é não-owner.

begin;

-- =====================================================================================
-- (1) Guarda de recência: carimba o timestamp do último evento aplicado por tenant.
-- =====================================================================================
alter table public.tenant_cobranca
  add column if not exists ultimo_evento_em timestamptz;

-- cobranca_aplicar v4: agora recebe p_evento_em (event.created) e RETORNA boolean (true = aplicou;
-- false = evento STALE, ignorado). Mudou o tipo de retorno e a assinatura → DROP antes do CREATE.
drop function if exists public.cobranca_aplicar(uuid, text, text, text, timestamptz, text);
create or replace function public.cobranca_aplicar(
  p_tenant uuid, p_customer text, p_subscription text,
  p_status text, p_period_end timestamptz, p_plano text, p_evento_em timestamptz
) returns boolean language plpgsql security definer set search_path = '' as $$
declare v_ultimo timestamptz;
begin
  select ultimo_evento_em into v_ultimo
    from public.tenant_cobranca where tenant_id = p_tenant;

  -- STALE: um evento mais ANTIGO que o último já aplicado não pode regredir o estado (Stripe entrega
  -- sem ordem garantida). Ex.: um 'updated' (active) reentregue DEPOIS do 'deleted' resurgiria a
  -- assinatura. Guardamos por event.created; NÃO por period_end (active↔past_due dividem o período).
  if p_evento_em is not null and v_ultimo is not null and p_evento_em < v_ultimo then
    return false;
  end if;

  -- COALESCE em status/current_period_end/subscription: um evento que não traz o campo (checkout, ou
  -- um payload Basil sem current_period_end no topo antes do fix no app) NUNCA zera o valor conhecido.
  insert into public.tenant_cobranca
    (tenant_id, stripe_customer_id, stripe_subscription_id, status, current_period_end, ultimo_evento_em)
  values (p_tenant, p_customer, p_subscription, p_status, p_period_end, p_evento_em)
  on conflict (tenant_id) do update set
    stripe_customer_id     = coalesce(excluded.stripe_customer_id,
                                      public.tenant_cobranca.stripe_customer_id),
    stripe_subscription_id = coalesce(excluded.stripe_subscription_id,
                                      public.tenant_cobranca.stripe_subscription_id),
    status                 = coalesce(excluded.status, public.tenant_cobranca.status),
    current_period_end     = coalesce(excluded.current_period_end,
                                      public.tenant_cobranca.current_period_end),
    ultimo_evento_em       = coalesce(excluded.ultimo_evento_em,
                                      public.tenant_cobranca.ultimo_evento_em);

  if p_plano is not null then
    insert into public.tenant_assinaturas (tenant_id, plano_codigo, origem, expira_em)
    values (p_tenant, p_plano, 'stripe', null)
    on conflict (tenant_id) do update set
      plano_codigo = excluded.plano_codigo,
      origem       = 'stripe',
      expira_em    = null;
    perform public.registrar_transicao_plano(p_tenant, p_plano, 'stripe', p_status);
  end if;
  return true;
end; $$;
alter function public.cobranca_aplicar(uuid, text, text, text, timestamptz, text, timestamptz)
  owner to postgres;
revoke all on function public.cobranca_aplicar(uuid, text, text, text, timestamptz, text, timestamptz)
  from public, anon;
grant execute on function public.cobranca_aplicar(uuid, text, text, text, timestamptz, text, timestamptz)
  to authenticated, cria_app;

-- =====================================================================================
-- (2) Ledger de avisos enviados (dedupe/throttle das jornadas). Default-deny (RLS on, sem policy):
--     só as funções definer abaixo escrevem/leem. chave = event.id / invoice / estágio / limiar.
-- =====================================================================================
create table if not exists public.cobranca_avisos (
  tenant_id  uuid        not null references public.profiles(id) on delete cascade,
  tipo       text        not null,   -- 'cartao_recusado'|'renovacao'|'cancelamento'|'winback'|'quota'|'overage'
  chave      text        not null,   -- dedupe: event.id, invoice, estágio winback, limiar de quota
  enviado_em timestamptz not null default now(),
  primary key (tenant_id, tipo, chave)
);
alter table public.cobranca_avisos enable row level security;

-- Reivindica um aviso ÚNICO (por chave): true SÓ na 1ª vez (insere) → o caller manda o e-mail.
-- Reentrega do mesmo evento Stripe → conflito → false → não reenvia.
create or replace function public.cobranca_aviso_uma_vez(p_tenant uuid, p_tipo text, p_chave text)
returns boolean language plpgsql volatile security definer set search_path = '' as $$
declare v_n int;
begin
  insert into public.cobranca_avisos (tenant_id, tipo, chave)
  values (p_tenant, p_tipo, p_chave)
  on conflict (tenant_id, tipo, chave) do nothing;
  get diagnostics v_n = row_count;
  return v_n > 0;
end; $$;
alter function public.cobranca_aviso_uma_vez(uuid, text, text) owner to postgres;
revoke all on function public.cobranca_aviso_uma_vez(uuid, text, text) from public, anon;
grant execute on function public.cobranca_aviso_uma_vez(uuid, text, text) to authenticated, cria_app;

-- Reivindica um aviso PERIÓDICO (re-envia só após p_intervalo): true na 1ª vez OU quando o último
-- envio já passou do intervalo (e re-carimba). Usado no nudge de quota (re-lembra a cada N dias
-- enquanto o espaço seguir cheio), sem spammar a cada varredura/upload.
create or replace function public.cobranca_aviso_periodico(
  p_tenant uuid, p_tipo text, p_chave text, p_intervalo interval
) returns boolean language plpgsql volatile security definer set search_path = '' as $$
declare v_deve boolean;
begin
  insert into public.cobranca_avisos (tenant_id, tipo, chave)
  values (p_tenant, p_tipo, p_chave)
  on conflict (tenant_id, tipo, chave) do update
    set enviado_em = now()
    where public.cobranca_avisos.enviado_em < now() - p_intervalo
  returning true into v_deve;
  return coalesce(v_deve, false);
end; $$;
alter function public.cobranca_aviso_periodico(uuid, text, text, interval) owner to postgres;
revoke all on function public.cobranca_aviso_periodico(uuid, text, text, interval) from public, anon;
grant execute on function public.cobranca_aviso_periodico(uuid, text, text, interval)
  to authenticated, cria_app;

-- =====================================================================================
-- (3) Win-back: tenants que caíram de plano PAGO → free e SEGUEM free (época vigente free, cuja
--     origem foi o fim de uma época paga). Cross-tenant (o reaper roda como cria_app sem JWT).
-- =====================================================================================
create or replace function public.cobranca_winback_candidatos(p_dias int, p_limit int)
returns table (tenant_id uuid, email text, nome text, caiu_em timestamptz, dias int)
language sql stable security definer set search_path = '' as $$
  select r.tenant_id, p.email::text, p.nome, r.inicio,
         floor(extract(epoch from now() - r.inicio) / 86400)::int
  from public.tenant_plano_historico r
  join public.profiles p on p.id = r.tenant_id
  where r.fim is null                                   -- época vigente (não reassinou)
    and r.plano_codigo = 'free'
    and r.inicio >= now() - make_interval(days => p_dias)
    and exists (
      select 1 from public.tenant_plano_historico r2
      where r2.tenant_id = r.tenant_id and r2.plano_codigo <> 'free' and r2.fim = r.inicio
    )
  order by r.inicio desc
  limit greatest(1, least(coalesce(p_limit, 200), 500));
$$;
alter function public.cobranca_winback_candidatos(int, int) owner to postgres;
revoke all on function public.cobranca_winback_candidatos(int, int) from public, anon, authenticated;
grant execute on function public.cobranca_winback_candidatos(int, int) to cria_app;

-- Elegibilidade individual ao cupom de win-back (o próprio tenant, no re-checkout): caiu de pago→free
-- e SEGUE free. Gate p/ o promo não poder ser auto-aplicado por qualquer um. auth-scoped.
create or replace function public.cobranca_elegivel_winback(p_tenant uuid)
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.tenant_plano_historico r
    where r.tenant_id = p_tenant and r.fim is null and r.plano_codigo = 'free'
      and exists (
        select 1 from public.tenant_plano_historico r2
        where r2.tenant_id = r.tenant_id and r2.plano_codigo <> 'free' and r2.fim = r.inicio
      )
  );
$$;
alter function public.cobranca_elegivel_winback(uuid) owner to postgres;
revoke all on function public.cobranca_elegivel_winback(uuid) from public, anon;
grant execute on function public.cobranca_elegivel_winback(uuid) to authenticated, cria_app;

-- Up-sell de GB: assinantes PAGOS (podem contratar add-on) que encostaram em p_pct% do limite EFETIVO
-- de storage. Escopado só aos pagos (não é scan de todos os tenants — o reaper varre este conjunto
-- pequeno) e com limite finito. usado/limite calculados 1x no lateral. Definer (cross-tenant, cria_app).
create or replace function public.cobranca_upsell_storage_candidatos(p_pct int, p_limit int)
returns table (tenant_id uuid, email text, nome text, pct int)
language sql stable security definer set search_path = '' as $$
  select c.tenant_id, p.email::text, p.nome,
         floor(x.usado::numeric / (x.lim_mb::bigint * 1024 * 1024) * 100)::int as pct
  from public.tenant_cobranca c
  join public.profiles p on p.id = c.tenant_id
  cross join lateral (
    select public.limite_armazenamento_mb(c.tenant_id) as lim_mb,
           public.consumo_armazenamento_bytes(c.tenant_id) as usado
  ) x
  where c.status in ('active', 'trialing', 'past_due')
    and x.lim_mb > 0                                               -- ignora ilimitado (-1) e zero
    and x.usado >= (x.lim_mb::bigint * 1024 * 1024) * p_pct / 100.0
  order by pct desc
  limit greatest(1, least(coalesce(p_limit, 200), 500));
$$;
alter function public.cobranca_upsell_storage_candidatos(int, int) owner to postgres;
revoke all on function public.cobranca_upsell_storage_candidatos(int, int)
  from public, anon, authenticated;
grant execute on function public.cobranca_upsell_storage_candidatos(int, int) to cria_app;

-- =====================================================================================
-- (4) Contato do arquiteto (e-mail/nome) p/ os avisos, resolvido dentro do webhook (cria_app).
-- =====================================================================================
create or replace function public.cobranca_contato(p_tenant uuid)
returns table (email text, nome text)
language sql stable security definer set search_path = '' as $$
  select p.email::text, p.nome from public.profiles p where p.id = p_tenant;
$$;
alter function public.cobranca_contato(uuid) owner to postgres;
revoke all on function public.cobranca_contato(uuid) from public, anon;
grant execute on function public.cobranca_contato(uuid) to authenticated, cria_app;

create or replace function public.cobranca_contato_por_customer(p_customer text)
returns table (tenant_id uuid, email text, nome text)
language sql stable security definer set search_path = '' as $$
  select c.tenant_id, p.email::text, p.nome
  from public.tenant_cobranca c
  join public.profiles p on p.id = c.tenant_id
  where c.stripe_customer_id = p_customer;
$$;
alter function public.cobranca_contato_por_customer(text) owner to postgres;
revoke all on function public.cobranca_contato_por_customer(text) from public, anon, authenticated;
grant execute on function public.cobranca_contato_por_customer(text) to cria_app;

commit;
