-- 0108_armazenamento_alocacao.sql  (Admin — alocar espaço por cliente + reserva do pool)
--
-- CONTEXTO: o storage de produção é o Google Drive (5 TB) atrás do StorageBackend. A cota por cliente
-- já existe (0033/0042/0107: consumo_armazenamento_bytes + trigger enforce_quota_armazenamento lendo
-- plano_limite(...,'armazenamento_mb')). Aqui o admin passa a ALOCAR mais/menos espaço por cliente,
-- ACIMA (ou abaixo) do que o plano dá, e esse extra vira uma RESERVA visível no painel do pool.
--
-- Dois números DISTINTOS (não confundir — foi a origem do "cálculo do Drive errado"):
--   • CONSUMO CONTABILIZADO (consumo_armazenamento_bytes) = Σ tamanho_bytes do 'full'/raw. É o que a
--     cota cobra. NÃO inclui as miniaturas (thumb.jpg) — elas são overhead grátis.
--   • ESPAÇO REAL NO DRIVE = o que de fato ocupa os 5 TB (inclui miniaturas, Gmail, Fotos, lixeira).
--     Vem do próprio Drive (about.storageQuota), não deste banco. Ver services/storage/drive.py.
-- O painel mostra os dois lado a lado, rotulados, pra nunca somar pasta-a-pasta e comparar com a cota.
--
-- Aplicar como postgres (SQL Editor / db push), DEPOIS do 0107. A conexão cria_app é não-owner.
-- Depois de aplicar, faça o DEPLOY do backend (planos.py e admin passam a ler a função nova).

begin;

-- =====================================================================================
-- (1) Override por cliente: espaço EXTRA (MB) somado ao limite do plano. Pode ser NEGATIVO (reduzir
--     abaixo do plano p/ um abusador). Default-deny (só as funções definer leem/escrevem).
-- =====================================================================================
create table if not exists public.tenant_armazenamento (
  tenant_id              uuid        primary key references public.profiles(id) on delete cascade,
  armazenamento_mb_extra bigint      not null default 0,
  atualizado_por         uuid        references public.profiles(id) on delete set null,
  updated_at             timestamptz not null default now()
);
alter table public.tenant_armazenamento enable row level security;
drop trigger if exists trg_tenant_armazenamento_updated_at on public.tenant_armazenamento;
create trigger trg_tenant_armazenamento_updated_at
  before update on public.tenant_armazenamento for each row execute function public.set_updated_at();

-- =====================================================================================
-- (2) LIMITE EFETIVO de armazenamento (MB) = plano + extra. -1 (plano ilimitado) manda e ignora o
--     extra; senão faz o clamp em >= 0 (extra negativo não vira limite negativo).
--     Usada pelo TRIGGER de quota e pelo painel /me (get_quota). Roda em contexto do PRÓPRIO tenant
--     (pode_ler_tenant(self)=true dentro de plano_do_tenant) — o painel admin NÃO chama esta (ele
--     resolve o limite efetivo inline, sem o gate pode_ler_tenant; ver (4)).
-- =====================================================================================
create or replace function public.limite_armazenamento_mb(p_tenant uuid)
returns bigint
language plpgsql stable security definer set search_path = '' as $$
declare v_base bigint; v_extra bigint;
begin
  v_base := public.plano_limite(p_tenant, 'armazenamento_mb');
  if v_base < 0 then
    return -1;                                  -- plano ilimitado: extra não se aplica
  end if;
  select coalesce(te.armazenamento_mb_extra, 0) into v_extra
    from public.tenant_armazenamento te where te.tenant_id = p_tenant;
  return greatest(0, v_base + coalesce(v_extra, 0));
end; $$;
alter function public.limite_armazenamento_mb(uuid) owner to postgres;
revoke all on function public.limite_armazenamento_mb(uuid) from public, anon;
grant execute on function public.limite_armazenamento_mb(uuid) to authenticated;

-- =====================================================================================
-- (3) O guard de quota passa a enforçar o limite EFETIVO (antes lia só plano_limite). Mesmo corpo do
--     0042/0107 — só troca a fonte do limite. Mensagem parseável pelo backend inalterada.
-- =====================================================================================
create or replace function public.enforce_quota_armazenamento()
returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_limite_mb bigint;
  v_limite_b  bigint;
  v_usado     bigint;
begin
  v_limite_mb := public.limite_armazenamento_mb(new.tenant_id);   -- plano + extra alocado
  if v_limite_mb < 0 then
    return new;                                       -- ilimitado
  end if;
  perform pg_advisory_xact_lock(hashtext('cria:quota_armazenamento'), hashtext(new.tenant_id::text));
  v_limite_b := v_limite_mb * 1024 * 1024;
  v_usado := public.consumo_armazenamento_bytes(new.tenant_id);   -- anexos+moodboard+revisao+portal+logo
  if v_usado + new.tamanho_bytes > v_limite_b then
    raise exception 'limite_armazenamento:%:%', v_limite_mb, v_usado using errcode = 'P0001';
  end if;
  return new;
end;
$$;
alter function public.enforce_quota_armazenamento() owner to postgres;

-- =====================================================================================
-- (4) admin_listar_tenants v4: + armazenamento_limite_mb (EFETIVO) e armazenamento_extra_mb (o
--     override). Ganhou colunas no retorno → DROP antes. Mantém TODO o corpo do 0094 (escopo a
--     arquitetos, plano efetivo, último pagto/login/atividade). O limite efetivo é resolvido INLINE
--     a partir do plano efetivo já calculado (ef) + extra — NÃO chama limite_armazenamento_mb() pra
--     não passar pelo gate pode_ler_tenant (o admin lê o tenant de OUTRO usuário).
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
  armazenamento_limite_mb bigint,   -- limite EFETIVO (plano + extra); -1 = ilimitado
  armazenamento_extra_mb  bigint    -- override alocado pelo admin (0 = sem extra)
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
           else greatest(0, ef.armaz_mb + coalesce(ta.armazenamento_mb_extra, 0)) end,
      coalesce(ta.armazenamento_mb_extra, 0)
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

-- =====================================================================================
-- (5) admin: definir o extra alocado (a "reserva"). Idempotente (upsert). Registra na auditoria.
--     p_extra_mb pode ser negativo. Zerar (0) remove a alocação na prática (limite volta ao do plano).
-- =====================================================================================
create or replace function public.admin_definir_armazenamento_extra(p_tenant uuid, p_extra_mb bigint)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  if not exists (select 1 from public.profiles where id = p_tenant) then
    raise exception 'cliente inexistente' using errcode = '23503';
  end if;
  insert into public.tenant_armazenamento (tenant_id, armazenamento_mb_extra, atualizado_por)
  values (p_tenant, coalesce(p_extra_mb, 0), (select auth.uid()))
  on conflict (tenant_id) do update set
    armazenamento_mb_extra = excluded.armazenamento_mb_extra,
    atualizado_por         = excluded.atualizado_por,
    updated_at             = now();
  perform public.admin_log_registrar('armazenamento_extra', p_tenant,
    jsonb_build_object('extra_mb', coalesce(p_extra_mb, 0)));
end; $$;
alter function public.admin_definir_armazenamento_extra(uuid, bigint) owner to postgres;
revoke all on function public.admin_definir_armazenamento_extra(uuid, bigint) from public, anon;
grant execute on function public.admin_definir_armazenamento_extra(uuid, bigint) to authenticated;

commit;
