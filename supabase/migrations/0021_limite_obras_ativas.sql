-- 0021_limite_obras_ativas.sql  (Fase 2 — enforcement do eixo "obras ativas")
-- Trava race-safe (advisory lock por tenant) integrada a criar_obra e reativar_obra.
-- Downgrade = grandfathering: nada é arquivado; só a PRÓXIMA ação que consome vaga bloqueia.

-- Checagem central. Advisory lock transaction-scoped serializa só o MESMO tenant.
-- Em READ COMMITTED, o 2º request (após o lock liberar no commit do 1º) já vê a obra nova.
create or replace function public._checar_vaga_obra_ativa(p_tenant uuid)
returns void
language plpgsql security definer set search_path = '' as $$
declare
  v_limite bigint;
  v_ativas bigint;
begin
  perform pg_advisory_xact_lock(hashtext('cria:limite_obras_ativas'), hashtext(p_tenant::text));
  v_limite := public.plano_limite(p_tenant, 'obras_ativas');
  if v_limite < 0 then
    return;                                   -- -1 = ilimitado
  end if;
  select count(*) into v_ativas
  from public.obras o
  where o.tenant_id = p_tenant and o.status = 'ativa';
  if v_ativas >= v_limite then
    -- mensagem PARSEÁVEL pelo backend (P0001 é genérico). Se mudar, mudar o parser junto.
    raise exception 'limite_obras_ativas:%:%', v_limite, v_ativas using errcode = 'P0001';
  end if;
end; $$;
alter function public._checar_vaga_obra_ativa(uuid) owner to postgres;
-- Só chamada por outras funções SECURITY DEFINER (não diretamente pela app):
revoke all on function public._checar_vaga_obra_ativa(uuid) from public, anon, authenticated;

-- criar_obra v2: checa a vaga apenas quando a obra é NOVA (idempotência por id offline).
create or replace function public.criar_obra(p_id uuid, p_nome text)
returns table (id uuid, nome text, status public.status_obra, seq_humano bigint, created_at timestamptz)
language plpgsql security definer set search_path = '' as $$
declare
  v_uid    uuid := (select auth.uid());
  v_existe boolean;
begin
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;

  select exists (select 1 from public.obras o where o.id = p_id) into v_existe;
  if not v_existe then
    perform public._checar_vaga_obra_ativa(v_uid);   -- bloqueia (P0001) se sem vaga
  end if;

  insert into public.obras (id, tenant_id, nome)
  values (p_id, v_uid, p_nome)
  on conflict (id) do nothing;

  if found then
    insert into public.obra_membros (obra_id, profile_id, papel, estado, invited_by)
    values (p_id, v_uid, 'arquiteto', 'ativo', v_uid)
    on conflict (obra_id, profile_id) do nothing;
  end if;

  return query
    select o.id, o.nome, o.status, o.seq_humano, o.created_at
    from public.obras o
    where o.id = p_id and o.tenant_id = v_uid;
end; $$;
alter function public.criar_obra(uuid, text) owner to postgres;
revoke all on function public.criar_obra(uuid, text) from public, anon;
grant execute on function public.criar_obra(uuid, text) to authenticated;

-- reativar_obra: reativar consome vaga -> mesma checagem do criar (BORDA 1).
-- Idempotente (já ativa = no-op). Valida existência (P0002->404) e papel (42501->403).
create or replace function public.reativar_obra(p_id uuid)
returns table (id uuid, nome text, status public.status_obra, seq_humano bigint, created_at timestamptz)
language plpgsql security definer set search_path = '' as $$
declare
  v_uid    uuid := (select auth.uid());
  v_tenant uuid;
  v_status public.status_obra;
begin
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;

  select o.tenant_id, o.status into v_tenant, v_status
  from public.obras o where o.id = p_id
  for update;                                  -- serializa reativar/arquivar da mesma obra

  if v_tenant is null then
    raise exception 'obra inexistente' using errcode = 'P0002';
  end if;
  if not public.is_arquiteto_ativo(p_id) then
    raise exception 'apenas arquiteto pode reativar' using errcode = '42501';
  end if;

  if v_status <> 'ativa' then
    perform public._checar_vaga_obra_ativa(v_tenant);   -- bloqueia (P0001) se sem vaga
    update public.obras set status = 'ativa' where id = p_id;
  end if;

  return query
    select o.id, o.nome, o.status, o.seq_humano, o.created_at
    from public.obras o where o.id = p_id;
end; $$;
alter function public.reativar_obra(uuid) owner to postgres;
revoke all on function public.reativar_obra(uuid) from public, anon;
grant execute on function public.reativar_obra(uuid) to authenticated;
