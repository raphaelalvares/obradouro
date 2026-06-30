-- 0094_atividade_usuario.sql  (Último login + última ação de cada usuário no painel admin)
--
-- O painel admin precisa mostrar, por cliente (arquiteto), o ÚLTIMO LOGIN e a ÚLTIMA AÇÃO:
--   • último login  → auth.users.last_sign_in_at (o GoTrue já mantém; sem escrita extra nossa).
--   • última ação   → public.profiles.ultima_atividade_em, que ESTE arquivo passa a manter: cada
--     request autenticado chama tocar_atividade(), com THROTTLE de 5 min (não escreve a cada request).
--
-- Aplicar como postgres (SQL Editor / db push), DEPOIS do 0093. Depende de 0090 (admin_listar_tenants
-- + is_platform_admin) e 0091 (colunas de billing no retorno). A função lê auth.users — roda como o
-- owner (postgres), que tem acesso ao schema auth no Supabase.

begin;

-- =====================================================================================
-- (1) Carimbo da última atividade (última ação no app), atualizado pelo backend a cada request.
-- =====================================================================================
alter table public.profiles
  add column if not exists ultima_atividade_em timestamptz;

-- Marca "ativo agora" para o auth.uid() corrente, com throttle: só escreve se passou > 5 min do
-- último carimbo (evita 1 UPDATE por request). A identidade vem SEMPRE de auth.uid() (nunca de
-- argumento) → o usuário só carimba a si mesmo; webhook/cria_app (auth.uid() NULL) é no-op.
create or replace function public.tocar_atividade()
returns void language plpgsql security definer set search_path = '' as $$
begin
  if (select auth.uid()) is null then
    return;
  end if;
  update public.profiles
     set ultima_atividade_em = now()
   where id = (select auth.uid())
     and (ultima_atividade_em is null or ultima_atividade_em < now() - interval '5 minutes');
end; $$;
alter function public.tocar_atividade() owner to postgres;
revoke all on function public.tocar_atividade() from public, anon;
grant execute on function public.tocar_atividade() to authenticated;

-- =====================================================================================
-- (2) admin_listar_tenants v3: + ultimo_login (auth.users.last_sign_in_at) e ultima_atividade_em
--     (public.profiles). Ganhou colunas no retorno → DROP antes (create or replace não muda o tipo
--     de retorno). Mantém TODO o corpo do 0091 (escopo a arquitetos, plano efetivo, último pagto).
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
  ultimo_login        timestamptz,   -- auth.users.last_sign_in_at (último login)
  ultima_atividade_em timestamptz    -- public.profiles.ultima_atividade_em (última ação no app)
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
      p.ultima_atividade_em
    from public.profiles p
    left join public.tenant_assinaturas a on a.tenant_id = p.id
    left join public.tenant_branding    b on b.tenant_id = p.id
    left join public.tenant_cobranca    c on c.tenant_id = p.id
    left join auth.users                au on au.id = p.id
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

commit;
