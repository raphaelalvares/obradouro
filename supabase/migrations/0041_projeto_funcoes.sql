-- 0041_projeto_funcoes.sql  (Fase 5 — RPCs SECURITY DEFINER dos fluxos "ovo-e-galinha" com a RLS)
-- criar_projeto: criador ainda não é membro no INSERT. resgatar_codigo_projeto: quem entra ainda
-- não é membro. subir_revisao: aloca numero sob lock por projeto. Todas:
--  - DERIVAM identidade do contexto (auth.uid()), nunca confiam no chamador;
--  - NUNCA ON CONFLICT em tabela com trigger de seq (queima seq) → exists-check + subtxn;
--  - usam #variable_conflict use_column (lição do 0027: OUT param vs coluna).
-- Auditoria desses eventos é feita pela aplicação (mesma txn), via cria_audit_log de 11 args (0038).

-- ===================== criar_projeto =====================
create or replace function public.criar_projeto(p_id uuid, p_nome text, p_briefing jsonb)
returns table (id uuid, nome text, obra_id uuid, seq_humano bigint, created_at timestamptz)
language plpgsql security definer set search_path = '' as $$
#variable_conflict use_column
declare
  v_uid uuid := (select auth.uid());
begin
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;

  -- idempotência offline SEM queimar seq (NÃO usar ON CONFLICT em tabela com trigger de seq)
  if exists (select 1 from public.projetos pj where pj.id = p_id) then
    return query
      select pj.id, pj.nome, pj.obra_id, pj.seq_humano, pj.created_at
      from public.projetos pj where pj.id = p_id and pj.tenant_id = v_uid;
    return;
  end if;

  begin
    insert into public.projetos (id, tenant_id, nome, briefing, created_by)
    values (p_id, v_uid, p_nome, coalesce(p_briefing, '{}'::jsonb), v_uid);
  exception when unique_violation then            -- corrida no mesmo uuid (subtxn reverte o seq)
    return query
      select pj.id, pj.nome, pj.obra_id, pj.seq_humano, pj.created_at
      from public.projetos pj where pj.id = p_id and pj.tenant_id = v_uid;
    return;
  end;

  -- vínculo do criador (arquiteto/ativo). projeto_membros NÃO tem seq → on conflict é seguro.
  insert into public.projeto_membros (projeto_id, profile_id, papel, estado, invited_by)
  values (p_id, v_uid, 'arquiteto', 'ativo', v_uid)
  on conflict (projeto_id, profile_id) do nothing;

  return query
    select pj.id, pj.nome, pj.obra_id, pj.seq_humano, pj.created_at
    from public.projetos pj where pj.id = p_id and pj.tenant_id = v_uid;
end;
$$;
alter function public.criar_projeto(uuid, text, jsonb) owner to postgres;
revoke all on function public.criar_projeto(uuid, text, jsonb) from public, anon;
grant execute on function public.criar_projeto(uuid, text, jsonb) to authenticated;

-- ===================== resgatar_codigo_projeto =====================
-- Cria vínculo PENDENTE; devolve o ESTADO atual (p/ o backend dar feedback: "convite pendente,
-- aceite" vs "já é membro"). Código NÃO auto-aceita (aceite é ato explícito do convidado).
create or replace function public.resgatar_codigo_projeto(p_codigo text)
returns table (projeto_id uuid, estado public.estado_membro)
language plpgsql security definer set search_path = '' as $$
#variable_conflict use_column
declare
  v_projeto uuid;
  v_papel   public.papel_obra;
  v_inviter uuid;
  v_uid     uuid := (select auth.uid());
begin
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;

  select c.projeto_id, c.papel, c.created_by
    into v_projeto, v_papel, v_inviter
  from public.projeto_codigos c
  where c.codigo = p_codigo and c.revoked_at is null and c.expires_at > now()
  for share;                                       -- evita corrida com revogação

  if v_projeto is null then
    raise exception 'codigo invalido ou expirado' using errcode = '22023';
  end if;

  -- uso único por pessoa (uq projeto_id+profile_id). on conflict do nothing é SEGURO (sem seq).
  insert into public.projeto_membros (projeto_id, profile_id, papel, estado, invited_by)
  values (v_projeto, v_uid, v_papel, 'pendente', v_inviter)
  on conflict (projeto_id, profile_id) do nothing;

  return query
    select pm.projeto_id, pm.estado
    from public.projeto_membros pm
    where pm.projeto_id = v_projeto and pm.profile_id = v_uid;
end;
$$;
alter function public.resgatar_codigo_projeto(text) owner to postgres;
revoke all on function public.resgatar_codigo_projeto(text) from public, anon;
grant execute on function public.resgatar_codigo_projeto(text) to authenticated;

-- ===================== subir_revisao =====================
-- Aloca numero (R0,R1…) sob advisory lock por projeto; garante UMA pendente por projeto. Autorização
-- ANTES de ler max/lock (não vaza numero/contention de projeto alheio). A sinalização "além do
-- incluído" NÃO é gravada aqui: é calculada AO VIVO (projetos.revisoes_incluidas vs numero) na
-- leitura. Os ARQUIVOS da revisão vão pelo StorageBackend (backend).
create or replace function public.subir_revisao(p_id uuid, p_projeto uuid, p_titulo text)
returns table (id uuid, projeto_id uuid, numero int, titulo text, status public.status_revisao,
               seq_humano bigint, created_at timestamptz)
language plpgsql security definer set search_path = '' as $$
#variable_conflict use_column
declare
  v_uid    uuid := (select auth.uid());
  v_tenant uuid;
  v_numero int;
begin
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;

  -- 1) AUTORIZAÇÃO antes de qualquer leitura/lock (definer ignora RLS → checar explicitamente)
  if not public.is_arquiteto_ativo_projeto(p_projeto) then
    raise exception 'apenas arquiteto cria revisao' using errcode = '42501';
  end if;
  select pj.tenant_id into v_tenant from public.projetos pj where pj.id = p_projeto;
  if v_tenant is null then
    raise exception 'projeto inexistente' using errcode = '23503';
  end if;

  -- 2) idempotência offline SEM queimar seq
  if exists (select 1 from public.revisoes r where r.id = p_id) then
    return query
      select r.id, r.projeto_id, r.numero, r.titulo, r.status,
             r.seq_humano, r.created_at
      from public.revisoes r where r.id = p_id and r.tenant_id = v_tenant;
    return;
  end if;

  -- 3) seção crítica: serializa por PROJETO (padrão do repo: hashtext(uuid::text))
  perform pg_advisory_xact_lock(hashtext('cria:revisao_numero'), hashtext(p_projeto::text));

  -- re-checa o MESMO id dentro do lock: uma corrida no mesmo uuid pode ter inserido enquanto
  -- esperávamos o lock → devolve a existente (idempotente), NÃO confunde com "outra pendente".
  if exists (select 1 from public.revisoes r where r.id = p_id) then
    return query
      select r.id, r.projeto_id, r.numero, r.titulo, r.status,
             r.seq_humano, r.created_at
      from public.revisoes r where r.id = p_id and r.tenant_id = v_tenant;
    return;
  end if;

  -- invariante "uma pendente por projeto" DENTRO do lock (rede final = uq_revisao_pendente)
  if exists (select 1 from public.revisoes r where r.projeto_id = p_projeto and r.status = 'pendente') then
    raise exception 'revisao_pendente_existe' using errcode = 'P0001';   -- backend → 409
  end if;

  v_numero := coalesce((select max(r.numero) from public.revisoes r where r.projeto_id = p_projeto), -1) + 1;

  begin
    insert into public.revisoes
      (id, projeto_id, tenant_id, numero, titulo, status, created_by)
    values (p_id, p_projeto, v_tenant, v_numero, p_titulo, 'pendente', v_uid);
  exception when unique_violation then            -- corrida no mesmo uuid (subtxn reverte seq)
    return query
      select r.id, r.projeto_id, r.numero, r.titulo, r.status,
             r.seq_humano, r.created_at
      from public.revisoes r where r.id = p_id and r.tenant_id = v_tenant;
    return;
  end;

  return query
    select r.id, r.projeto_id, r.numero, r.titulo, r.status,
           r.seq_humano, r.created_at
    from public.revisoes r where r.id = p_id;
end;
$$;
alter function public.subir_revisao(uuid, uuid, text) owner to postgres;
revoke all on function public.subir_revisao(uuid, uuid, text) from public, anon;
grant execute on function public.subir_revisao(uuid, uuid, text) to authenticated;
