-- 0018_funcoes_negocio.sql  (Fase 1)
-- Funções SECURITY DEFINER para os dois fluxos que têm "ovo-e-galinha" com a RLS:
--  - criar_obra: criador ainda não está em current_obra_ids() no INSERT.
--  - resgatar_codigo_obra: quem entra ainda não é membro (não passa na RLS de obra_codigos).
-- A auditoria desses eventos é feita pela aplicação (serviço de auditoria), na mesma transação.

-- Cria obra + vínculo do criador (arquiteto/ativo) atomicamente. Idempotente por id.
create or replace function public.criar_obra(p_id uuid, p_nome text)
returns table (id uuid, nome text, status public.status_obra, seq_humano bigint, created_at timestamptz)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid uuid := (select auth.uid());
begin
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;

  insert into public.obras (id, tenant_id, nome)
  values (p_id, v_uid, p_nome)
  on conflict (id) do nothing;

  if found then
    insert into public.obra_membros (obra_id, profile_id, papel, estado, invited_by)
    values (p_id, v_uid, 'arquiteto', 'ativo', v_uid)
    on conflict (obra_id, profile_id) do nothing;
  end if;

  -- retorna a obra do PRÓPRIO tenant (se p_id colidir com obra de outro, retorna vazio)
  return query
    select o.id, o.nome, o.status, o.seq_humano, o.created_at
    from public.obras o
    where o.id = p_id and o.tenant_id = v_uid;
end;
$$;

alter function public.criar_obra(uuid, text) owner to postgres;
revoke all on function public.criar_obra(uuid, text) from public, anon;
grant execute on function public.criar_obra(uuid, text) to authenticated;


-- Resgata um código de obra: cria o vínculo PENDENTE para o usuário atual.
create or replace function public.resgatar_codigo_obra(p_codigo text)
returns uuid                      -- retorna obra_id em caso de sucesso
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_obra    uuid;
  v_papel   public.papel_obra;
  v_inviter uuid;
begin
  select c.obra_id, c.papel, c.created_by
    into v_obra, v_papel, v_inviter
  from public.obra_codigos c
  where c.codigo = p_codigo
    and c.revoked_at is null
    and c.expires_at > now()
  for share;                       -- evita corrida com revogação

  if v_obra is null then
    raise exception 'codigo invalido ou expirado' using errcode = '22023';
  end if;

  -- uso único POR PESSOA: o unique(obra_id, profile_id) impede entrar 2x na mesma obra
  insert into public.obra_membros (obra_id, profile_id, papel, estado, invited_by)
  values (v_obra, (select auth.uid()), v_papel, 'pendente', v_inviter)
  on conflict (obra_id, profile_id) do nothing;

  return v_obra;
end;
$$;

alter function public.resgatar_codigo_obra(text) owner to postgres;
revoke all on function public.resgatar_codigo_obra(text) from public, anon;
grant execute on function public.resgatar_codigo_obra(text) to authenticated;
