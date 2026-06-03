-- 0027_fix_variable_conflict_obras.sql  (fix-forward de bug encontrado em teste ao vivo)
-- criar_obra/reativar_obra são `returns table(id, nome, status, ...)` → essas colunas viram
-- VARIÁVEIS PL/pgSQL. Como o corpo referencia `id` SEM qualificar (`on conflict (id)` no criar;
-- `where id = p_id` no reativar) e o plpgsql usa `#variable_conflict error` por padrão, o Postgres
-- levanta "column reference \"id\" is ambiguous" em runtime. ON CONFLICT não aceita qualificar a
-- coluna, então a correção é a diretiva `#variable_conflict use_column` (ambíguo → coluna).
-- Idempotente (create or replace). Mantém corpo idêntico ao 0021, só adiciona a diretiva.

create or replace function public.criar_obra(p_id uuid, p_nome text)
returns table (id uuid, nome text, status public.status_obra, seq_humano bigint, created_at timestamptz)
language plpgsql security definer set search_path = '' as $$
#variable_conflict use_column
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

create or replace function public.reativar_obra(p_id uuid)
returns table (id uuid, nome text, status public.status_obra, seq_humano bigint, created_at timestamptz)
language plpgsql security definer set search_path = '' as $$
#variable_conflict use_column
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
