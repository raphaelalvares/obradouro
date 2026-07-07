-- 0109_armazenamento_stripe.sql  (Armazenamento como ADD-ON self-service no Stripe)
--
-- CONTEXTO: o 0108 deu ao ADMIN a alocação manual de espaço (tenant_armazenamento.armazenamento_mb_extra).
-- Agora o próprio arquiteto CONTRATA espaço extra, pago no Stripe como ITEM RECORRENTE dentro da
-- assinatura que ele já tem (cobra pro-rata na hora, valor cheio no próximo ciclo). A FONTE DA VERDADE
-- da cota contratada é o Stripe: o webhook lê a quantidade do item de storage e grava aqui.
--
-- Duas fontes de extra, somadas ao plano:
--   • armazenamento_mb_contratado → dirigido pelo Stripe/webhook (self-service, pago).
--   • armazenamento_mb_extra      → cortesia MANUAL do admin (grátis; 0108), pode ser ±.
--
-- Aplicar como postgres (SQL Editor / db push), DEPOIS do 0108, ANTES do deploy do backend
-- (cobranca.py/planos.py passam a chamar as funções novas). A conexão cria_app é não-owner.

begin;

-- =====================================================================================
-- (1) 2ª fonte de extra: o que o cliente CONTRATOU via Stripe (>= 0; o webhook mantém em dia).
-- =====================================================================================
alter table public.tenant_armazenamento
  add column if not exists armazenamento_mb_contratado bigint not null default 0;

-- =====================================================================================
-- (2) LIMITE EFETIVO v2 = plano + cortesia(extra) + contratado. -1 (plano ilimitado) manda.
--     Mesmo contrato/grants do 0108 — só soma a nova parcela.
-- =====================================================================================
create or replace function public.limite_armazenamento_mb(p_tenant uuid)
returns bigint
language plpgsql stable security definer set search_path = '' as $$
declare v_base bigint; v_extra bigint; v_contr bigint;
begin
  v_base := public.plano_limite(p_tenant, 'armazenamento_mb');
  if v_base < 0 then
    return -1;                                  -- plano ilimitado: extras não se aplicam
  end if;
  select coalesce(te.armazenamento_mb_extra, 0), coalesce(te.armazenamento_mb_contratado, 0)
    into v_extra, v_contr
    from public.tenant_armazenamento te where te.tenant_id = p_tenant;
  return greatest(0, v_base + coalesce(v_extra, 0) + coalesce(v_contr, 0));
end; $$;
alter function public.limite_armazenamento_mb(uuid) owner to postgres;
revoke all on function public.limite_armazenamento_mb(uuid) from public, anon;
grant execute on function public.limite_armazenamento_mb(uuid) to authenticated;

-- =====================================================================================
-- (3) Setter do CONTRATADO. Caminho do WEBHOOK (cria_app, sem auth.uid()) e otimista do serviço
--     (authenticated, logo após aplicar no Stripe). Idempotente; clamp em >= 0.
-- =====================================================================================
create or replace function public.cobranca_set_armazenamento_contratado(p_tenant uuid, p_mb bigint)
returns void language plpgsql security definer set search_path = '' as $$
begin
  insert into public.tenant_armazenamento (tenant_id, armazenamento_mb_contratado)
  values (p_tenant, greatest(0, coalesce(p_mb, 0)))
  on conflict (tenant_id) do update set
    armazenamento_mb_contratado = greatest(0, coalesce(p_mb, 0)),
    updated_at                  = now();
end; $$;
alter function public.cobranca_set_armazenamento_contratado(uuid, bigint) owner to postgres;
revoke all on function public.cobranca_set_armazenamento_contratado(uuid, bigint) from public, anon;
grant execute on function public.cobranca_set_armazenamento_contratado(uuid, bigint)
  to authenticated, cria_app;

-- =====================================================================================
-- (4) Detalhamento do PRÓPRIO tenant p/ a área de Financeiro (base/cortesia/contratado/efetivo).
--     Contexto do próprio usuário (auth.uid()); definer só p/ ler tenant_armazenamento (default-deny).
-- =====================================================================================
create or replace function public.meu_armazenamento()
returns table (base_mb bigint, extra_mb bigint, contratado_mb bigint, efetivo_mb bigint)
language plpgsql stable security definer set search_path = '' as $$
declare v_uid uuid := (select auth.uid()); v_base bigint; v_extra bigint; v_contr bigint;
begin
  v_base := public.plano_limite(v_uid, 'armazenamento_mb');
  select coalesce(te.armazenamento_mb_extra, 0), coalesce(te.armazenamento_mb_contratado, 0)
    into v_extra, v_contr
    from public.tenant_armazenamento te where te.tenant_id = v_uid;
  return query select
    v_base,
    coalesce(v_extra, 0),
    coalesce(v_contr, 0),
    case when v_base < 0 then -1
         else greatest(0, v_base + coalesce(v_extra, 0) + coalesce(v_contr, 0)) end;
end; $$;
alter function public.meu_armazenamento() owner to postgres;
revoke all on function public.meu_armazenamento() from public, anon;
grant execute on function public.meu_armazenamento() to authenticated;

-- =====================================================================================
-- (5) Total COMPROMETIDO (Σ limites efetivos finitos de todos os tenants). Usada SÓ server-side
--     pelo backend p/ gatear a disponibilidade do pool ao contratar (o número não volta ao cliente;
--     API-only → não há RPC exposto). definer porque soma cross-tenant.
-- =====================================================================================
create or replace function public.armazenamento_comprometido_total_mb()
returns bigint language sql stable security definer set search_path = '' as $$
  select coalesce(sum(l), 0)::bigint
  from (select public.limite_armazenamento_mb(p.id) as l from public.profiles p) x
  where x.l > 0;
$$;
alter function public.armazenamento_comprometido_total_mb() owner to postgres;
revoke all on function public.armazenamento_comprometido_total_mb() from public, anon;
grant execute on function public.armazenamento_comprometido_total_mb() to authenticated;

-- =====================================================================================
-- (6) admin_listar_tenants v5: + armazenamento_contratado_mb; efetivo inline passa a somar o
--     contratado também. Preserva TODO o corpo do 0108/0094. DROP antes (muda o retorno).
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
  assinante_desde    timestamptz,
  ultimo_pagamento_em    timestamptz,
  ultimo_pagamento_cents bigint,
  obras_ativas       bigint,
  armazenamento_bytes bigint,
  created_at         timestamptz,
  ultimo_login        timestamptz,
  ultima_atividade_em timestamptz,
  armazenamento_limite_mb bigint,       -- limite EFETIVO (plano + cortesia + contratado); -1 = ilimitado
  armazenamento_extra_mb  bigint,       -- cortesia manual do admin (0108)
  armazenamento_contratado_mb bigint    -- contratado via Stripe (self-service)
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
      p.created_at,
      au.last_sign_in_at,
      p.ultima_atividade_em,
      case when ef.armaz_mb < 0 then -1
           else greatest(0, ef.armaz_mb
                            + coalesce(ta.armazenamento_mb_extra, 0)
                            + coalesce(ta.armazenamento_mb_contratado, 0)) end,
      coalesce(ta.armazenamento_mb_extra, 0),
      coalesce(ta.armazenamento_mb_contratado, 0)
    from public.profiles p
    left join public.tenant_assinaturas a on a.tenant_id = p.id
    left join public.tenant_branding    b on b.tenant_id = p.id
    left join public.tenant_cobranca    c on c.tenant_id = p.id
    left join public.tenant_armazenamento ta on ta.tenant_id = p.id
    left join auth.users                au on au.id = p.id
    left join lateral (
      select pl.codigo, pl.nome,
             coalesce((pl.limites ->> 'armazenamento_mb')::bigint, 0) as armaz_mb
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

commit;
