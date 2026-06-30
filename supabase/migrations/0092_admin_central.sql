-- 0092_admin_central.sql  (Central de admin — auditoria, notas, notificação de novo cadastro,
--                          gestão cross-tenant de e-mails de cliente nas obras)
--
-- Depende de 0089 (acessos_cliente + guard) e 0090 (platform_admins + is_platform_admin). Aplicar
-- como postgres, DEPOIS do 0091. Tudo cross-tenant via SECURITY DEFINER gateado por is_platform_admin.

begin;

-- =====================================================================================
-- (1) Log de auditoria das ações do admin. Default-deny (só funções definer leem/escrevem).
-- =====================================================================================
create table if not exists public.admin_log (
  id          uuid        primary key default gen_random_uuid(),
  admin_id    uuid        references public.profiles(id) on delete set null,
  acao        text        not null,
  tenant_alvo uuid        references public.profiles(id) on delete set null,
  detalhe     jsonb       not null default '{}'::jsonb,
  created_at  timestamptz not null default now()
);
create index if not exists ix_admin_log_created on public.admin_log (created_at desc);
alter table public.admin_log enable row level security;

-- Registra uma ação. Gateada (chamada por funções admin e pelo backend, sempre como o admin logado).
create or replace function public.admin_log_registrar(p_acao text, p_tenant uuid, p_detalhe jsonb)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  insert into public.admin_log (admin_id, acao, tenant_alvo, detalhe)
  values ((select auth.uid()), p_acao, p_tenant, coalesce(p_detalhe, '{}'::jsonb));
end; $$;
alter function public.admin_log_registrar(text, uuid, jsonb) owner to postgres;
revoke all on function public.admin_log_registrar(text, uuid, jsonb) from public, anon;
grant execute on function public.admin_log_registrar(text, uuid, jsonb) to authenticated;

create or replace function public.admin_log_listar(p_limit int)
returns table (
  id uuid, acao text, detalhe jsonb, created_at timestamptz,
  admin_email text, tenant_alvo uuid, tenant_email text
)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  return query
    select l.id, l.acao, l.detalhe, l.created_at,
           pa.email::text, l.tenant_alvo, pt.email::text
    from public.admin_log l
    left join public.profiles pa on pa.id = l.admin_id
    left join public.profiles pt on pt.id = l.tenant_alvo
    order by l.created_at desc
    limit greatest(1, least(coalesce(p_limit, 100), 500));
end; $$;
alter function public.admin_log_listar(int) owner to postgres;
revoke all on function public.admin_log_listar(int) from public, anon;
grant execute on function public.admin_log_listar(int) to authenticated;

-- =====================================================================================
-- (2) Notas internas por cliente (CRM-lite de suporte). Default-deny.
-- =====================================================================================
create table if not exists public.tenant_notas (
  id         uuid        primary key default gen_random_uuid(),
  tenant_id  uuid        not null references public.profiles(id) on delete cascade,
  autor_id   uuid        references public.profiles(id) on delete set null,
  texto      text        not null,
  created_at timestamptz not null default now()
);
create index if not exists ix_tenant_notas_tenant on public.tenant_notas (tenant_id, created_at desc);
alter table public.tenant_notas enable row level security;

create or replace function public.admin_notas_listar(p_tenant uuid)
returns table (id uuid, texto text, autor_email text, created_at timestamptz)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  return query
    select n.id, n.texto, pa.email::text, n.created_at
    from public.tenant_notas n
    left join public.profiles pa on pa.id = n.autor_id
    where n.tenant_id = p_tenant
    order by n.created_at desc;
end; $$;
alter function public.admin_notas_listar(uuid) owner to postgres;
revoke all on function public.admin_notas_listar(uuid) from public, anon;
grant execute on function public.admin_notas_listar(uuid) to authenticated;

create or replace function public.admin_nota_criar(p_tenant uuid, p_texto text)
returns uuid language plpgsql security definer set search_path = '' as $$
declare v_id uuid;
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  if coalesce(btrim(p_texto), '') = '' then
    raise exception 'nota vazia' using errcode = '22023';
  end if;
  insert into public.tenant_notas (tenant_id, autor_id, texto)
  values (p_tenant, (select auth.uid()), p_texto)
  returning id into v_id;
  return v_id;
end; $$;
alter function public.admin_nota_criar(uuid, text) owner to postgres;
revoke all on function public.admin_nota_criar(uuid, text) from public, anon;
grant execute on function public.admin_nota_criar(uuid, text) to authenticated;

create or replace function public.admin_nota_excluir(p_id uuid)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  delete from public.tenant_notas where id = p_id;
end; $$;
alter function public.admin_nota_excluir(uuid) owner to postgres;
revoke all on function public.admin_nota_excluir(uuid) from public, anon;
grant execute on function public.admin_nota_excluir(uuid) to authenticated;

-- =====================================================================================
-- (3) Notificação de novo cadastro: marca "visto até" por admin + conta novos arquitetos.
-- =====================================================================================
alter table public.platform_admins
  add column if not exists clientes_vistos_em timestamptz;

-- Conta arquitetos (mesma regra de admin_listar_tenants: exclui cliente-puro do portal) cadastrados
-- depois da última visita do admin corrente.
create or replace function public.admin_novos_count()
returns bigint language plpgsql stable security definer set search_path = '' as $$
declare n bigint; v_desde timestamptz;
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  select coalesce(clientes_vistos_em, 'epoch'::timestamptz) into v_desde
    from public.platform_admins where profile_id = (select auth.uid());
  select count(*) into n
    from public.profiles p
   where p.created_at > coalesce(v_desde, 'epoch'::timestamptz)
     and (
       (
         not exists (select 1 from public.obra_membros om
                      where om.profile_id = p.id and om.papel = 'cliente')
         and not exists (select 1 from public.projeto_membros pm
                          where pm.profile_id = p.id and pm.papel = 'cliente')
       )
       or exists (select 1 from public.obras o where o.tenant_id = p.id)
       or exists (select 1 from public.projetos pr where pr.tenant_id = p.id)
     );
  return coalesce(n, 0);
end; $$;
alter function public.admin_novos_count() owner to postgres;
revoke all on function public.admin_novos_count() from public, anon;
grant execute on function public.admin_novos_count() to authenticated;

create or replace function public.admin_marcar_vistos()
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  update public.platform_admins set clientes_vistos_em = now()
   where profile_id = (select auth.uid());
end; $$;
alter function public.admin_marcar_vistos() owner to postgres;
revoke all on function public.admin_marcar_vistos() from public, anon;
grant execute on function public.admin_marcar_vistos() to authenticated;

-- =====================================================================================
-- (4) Gestão cross-tenant de e-mails de cliente nas obras/projetos.
--     (4a) Liberar o guard p/ o admin agir em nome de qualquer tenant (sem isso o INSERT bate em
--          'tenant_id incoerente', pois auth.uid() do admin != tenant). Mantém TODA a regra p/
--          não-admin (anti cross-tenant + imutabilidade). Recria preservando o corpo do 0089.
-- =====================================================================================
create or replace function public.acessos_cliente_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  -- admin da plataforma age em nome de qualquer tenant (via funções admin_* definer); bypassa a
  -- coerência tenant=auth.uid (a coerência projeto/obra↔tenant é garantida por admin_autorizar_acesso).
  if public.is_platform_admin() then
    return case when tg_op = 'DELETE' then old else new end;
  end if;
  if tg_op = 'INSERT' then
    if new.tenant_id is distinct from (select auth.uid()) then
      raise exception 'tenant_id incoerente' using errcode = '42501';
    end if;
    if new.projeto_id is not null and not exists (
         select 1 from public.projetos p where p.id = new.projeto_id and p.tenant_id = new.tenant_id) then
      raise exception 'projeto de outro tenant' using errcode = '42501';
    end if;
    if new.obra_id is not null and not exists (
         select 1 from public.obras o where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'obra de outro tenant' using errcode = '42501';
    end if;
    return new;
  end if;
  if tg_op = 'UPDATE' then
    if new.id is distinct from old.id
       or new.tenant_id is distinct from old.tenant_id
       or new.projeto_id is distinct from old.projeto_id
       or new.obra_id is distinct from old.obra_id
       or new.email::text is distinct from old.email::text
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade do acesso e imutavel' using errcode = '42501';
    end if;
    return new;
  end if;
  return old;  -- DELETE
end;
$$;
alter function public.acessos_cliente_guard() owner to postgres;

-- (4b) Listar acessos de cliente de TODAS as obras/projetos de um tenant.
create or replace function public.admin_listar_acessos_cliente(p_tenant uuid)
returns table (
  id uuid, email text, estado text, cadastrado boolean,
  projeto_id uuid, obra_id uuid, alvo_nome text, created_at timestamptz
)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  return query
    select ac.id, ac.email::text, ac.estado, (ac.profile_id is not null),
           ac.projeto_id, ac.obra_id, coalesce(pj.nome, o.nome), ac.created_at
    from public.acessos_cliente ac
    left join public.projetos pj on pj.id = ac.projeto_id
    left join public.obras    o  on o.id  = ac.obra_id
    where ac.tenant_id = p_tenant
    order by ac.created_at desc;
end; $$;
alter function public.admin_listar_acessos_cliente(uuid) owner to postgres;
revoke all on function public.admin_listar_acessos_cliente(uuid) from public, anon;
grant execute on function public.admin_listar_acessos_cliente(uuid) to authenticated;

-- (4b-bis) Alvos (projetos + obras) do tenant — alimenta o seletor de "convidar cliente".
create or replace function public.admin_listar_alvos(p_tenant uuid)
returns table (id uuid, nome text, tipo text, obra_id uuid)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  return query
    select pj.id, pj.nome, 'projeto'::text, pj.obra_id
    from public.projetos pj where pj.tenant_id = p_tenant
    union all
    select o.id, o.nome, 'obra'::text, null::uuid
    from public.obras o where o.tenant_id = p_tenant
    order by 3, 2;
end; $$;
alter function public.admin_listar_alvos(uuid) owner to postgres;
revoke all on function public.admin_listar_alvos(uuid) from public, anon;
grant execute on function public.admin_listar_alvos(uuid) to authenticated;

-- (4c) Autorizar (convidar) um e-mail num projeto OU obra. Deriva o tenant do alvo (não confia em
--      input). Idempotente. Retorna o id do acesso.
create or replace function public.admin_autorizar_acesso(p_projeto uuid, p_obra uuid, p_email text)
returns uuid language plpgsql security definer set search_path = '' as $$
declare v_tenant uuid; v_id uuid;
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  if p_projeto is null and p_obra is null then
    raise exception 'informe projeto ou obra' using errcode = '22023';
  end if;
  if p_projeto is not null then
    select tenant_id into v_tenant from public.projetos where id = p_projeto;
  else
    select tenant_id into v_tenant from public.obras where id = p_obra;
  end if;
  if v_tenant is null then
    raise exception 'alvo inexistente' using errcode = '23503';
  end if;
  insert into public.acessos_cliente (tenant_id, projeto_id, obra_id, email)
  values (v_tenant, p_projeto, p_obra, p_email)
  on conflict do nothing
  returning id into v_id;
  if v_id is null then     -- já existia (idempotente): resolve o id (citext não opera sob search_path='')
    select id into v_id from public.acessos_cliente
     where tenant_id = v_tenant
       and lower(email::text) = lower(p_email)
       and projeto_id is not distinct from p_projeto
       and obra_id   is not distinct from p_obra
     limit 1;
  end if;
  perform public.admin_log_registrar('acesso_autorizado', v_tenant,
    jsonb_build_object('email', p_email, 'projeto_id', p_projeto, 'obra_id', p_obra));
  return v_id;
end; $$;
alter function public.admin_autorizar_acesso(uuid, uuid, text) owner to postgres;
revoke all on function public.admin_autorizar_acesso(uuid, uuid, text) from public, anon;
grant execute on function public.admin_autorizar_acesso(uuid, uuid, text) to authenticated;

-- (4d) Revogar um acesso + cascade dos vínculos materializados (replica _remover_vinculo_cliente).
create or replace function public.admin_revogar_acesso(p_acesso uuid)
returns void language plpgsql security definer set search_path = '' as $$
declare r record;
begin
  if not public.is_platform_admin() then
    raise exception 'acesso restrito ao admin da plataforma' using errcode = '42501';
  end if;
  delete from public.acessos_cliente where id = p_acesso
    returning tenant_id, projeto_id, obra_id, profile_id into r;
  if not found then
    return;
  end if;
  if r.profile_id is not null then
    if r.projeto_id is not null then
      delete from public.projeto_membros
       where projeto_id = r.projeto_id and profile_id = r.profile_id and papel = 'cliente';
      delete from public.obra_membros
       where profile_id = r.profile_id and papel = 'cliente'
         and obra_id = (select obra_id from public.projetos
                         where id = r.projeto_id and obra_id is not null);
    end if;
    if r.obra_id is not null then
      delete from public.obra_membros
       where obra_id = r.obra_id and profile_id = r.profile_id and papel = 'cliente';
    end if;
  end if;
  perform public.admin_log_registrar('acesso_revogado', r.tenant_id,
    jsonb_build_object('acesso_id', p_acesso));
end; $$;
alter function public.admin_revogar_acesso(uuid) owner to postgres;
revoke all on function public.admin_revogar_acesso(uuid) from public, anon;
grant execute on function public.admin_revogar_acesso(uuid) to authenticated;

commit;
