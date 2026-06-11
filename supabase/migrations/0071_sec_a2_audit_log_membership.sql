-- 0071_sec_a2_audit_log_membership.sql  (SEGURANÇA — Fase 2, item A2 / ALTO)
--
-- BUG (red-report Fase 1, A2): as duas sobrecargas de public.cria_audit_log já FORÇAM o ator a
-- auth.uid() e derivam tenant/label do contexto (0019/0038 — não confiam nos args de identidade),
-- MAS não checam se o ator é MEMBRO da obra/projeto do evento. A função tem grant a `authenticated`
-- (necessário: o backend grava o audit DENTRO da request, que roda com SET LOCAL ROLE authenticated —
-- app/services/audit.py). Via PostgREST direto (Path B), um usuário que conheça um obra_id/projeto_id
-- de OUTRO tenant podia chamar POST /rest/v1/rpc/cria_audit_log e INJETAR entradas forjadas no
-- audit_log da vítima (o append-only barra UPDATE/DELETE, não o INSERT fora de escopo).
--
-- CORREÇÃO (Opção A do red-report): a função passa a exigir que auth.uid() seja MEMBRO ATIVO da obra
-- (current_obra_ids) / do projeto (current_projeto_ids) do evento. Fecha a forja CROSS-TENANT (o
-- vetor que carrega a severidade). Mantém o grant a `authenticated` e a ATOMICIDADE (audit gravado na
-- mesma transação da mutação — propriedade central, não regredida).
--   Resíduo conhecido e ACEITO: um membro ainda pode inserir, via Path B, eventos auto-atribuídos na
--   PRÓPRIA obra/projeto (actor_id é forçado a auth.uid() → não personifica terceiros, não cruza
--   tenant, não altera entradas existentes). Baixo. O fechamento total ("audit system-only") é um item
--   de BACKLOG de arquitetura, ligado à verificação de exposição do schema no PostgREST — fechar lá
--   (config) é mais limpo que reescrever o caminho de audit (que perderia atomicidade). Ver
--   docs/security-fase1.md (A2 / Limites nº1).
--
-- NÃO QUEBRA NENHUM FLUXO (verificado caminho a caminho):
--   - criar_obra (0018) / criar_projeto (0041): inserem a membership ATIVA do criador ANTES de a
--     aplicação auditar (0018:5 é explícito) → ator já ativo → passa.
--   - aceitar_convite (convites.py / projeto_vinculo.py): o UPDATE estado='ativo' ocorre ANTES do
--     log_event (a mudança é visível na transação) → passa.
--   - resgatar (codigo.py:128): NÃO audita (pendente não enxerga a obra) → irrelevante.
--   - imports (0026/0043/0044/0049, `perform cria_audit_log`): rodam com auth.uid()=arquiteto ativo
--     → in current_obra_ids() → passa.
--   - eventos de tenant sem obra/projeto (catálogo/oportunidade/branding): v_tenant := auth.uid()
--     (próprio) → sem checagem de membership e sem cruzar tenant.
--
-- errcode 42501 (insufficient_privilege): o backend mapeia 42501→403; checa membership ANTES de
-- derivar o tenant → não-membro recebe a MESMA resposta para obra inexistente vs. sem-permissão (não
-- vira oráculo). Mantém SECURITY DEFINER + search_path='' e reafirma owner/grants (autossuficiente;
-- o grant a `authenticated` CONTINUA — o backend precisa dele). Aplicar como postgres, DEPOIS da 0038.
-- DEV antes de PROD.
--
-- VERIFICAR após aplicar:
--   -- (1) grant a authenticated CONTINUA nas 2 sobrecargas (10 e 11 args):
--   select routine_name, grantee, privilege_type from information_schema.role_routine_grants
--   where routine_schema='public' and routine_name='cria_audit_log';
--   -- (2) regressão funcional: criar obra/projeto, aceitar um convite e editar um item devem gravar
--   --     o histórico normalmente (GET /obras/{id}/audit e /projetos/{id}/audit não-vazios).
--   -- (3) ataque negado: como usuário A (não-membro), chamar cria_audit_log com p_obra de B → 42501.

begin;

-- ---------- sobrecarga de 10 args (eventos de OBRA) — base 0019 + membership-check ----------
create or replace function public.cria_audit_log(
  p_tenant uuid, p_actor uuid, p_obra uuid, p_action text, p_entity_type text,
  p_entity_id uuid, p_changed jsonb, p_entity_label text,
  p_entity_seq bigint, p_actor_label text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_uid    uuid := (select auth.uid());
  v_tenant uuid;
  v_label  text;
begin
  -- p_tenant/p_actor/p_actor_label são IGNORADOS de propósito (não confiar no chamador).
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;

  if p_obra is not null then
    -- A2: o ator tem de ser MEMBRO ATIVO da obra do evento (anti-forja cross-tenant via Path B).
    -- Checado ANTES de derivar o tenant → não vaza "existe vs. sem permissao".
    if p_obra not in (select public.current_obra_ids()) then
      raise exception 'sem permissao na obra do evento' using errcode = '42501';
    end if;
    select o.tenant_id into v_tenant from public.obras o where o.id = p_obra;
    if v_tenant is null then
      raise exception 'obra inexistente' using errcode = '23503';
    end if;
  else
    v_tenant := v_uid;
  end if;

  select coalesce(pr.nome, pr.email::text) into v_label
  from public.profiles pr where pr.id = v_uid;

  insert into public.audit_log
    (tenant_id, actor_id, obra_id, action, entity_type, entity_id, changed,
     entity_label, entity_seq, actor_label)
  values
    (v_tenant, v_uid, p_obra, p_action, p_entity_type, p_entity_id, p_changed,
     p_entity_label, p_entity_seq, v_label);
end;
$$;
alter function public.cria_audit_log(uuid, uuid, uuid, text, text, uuid, jsonb, text, bigint, text)
  owner to postgres;
revoke all on function public.cria_audit_log(uuid, uuid, uuid, text, text, uuid, jsonb, text, bigint, text)
  from public, anon;
grant execute on function public.cria_audit_log(uuid, uuid, uuid, text, text, uuid, jsonb, text, bigint, text)
  to authenticated;

-- ---------- sobrecarga de 11 args (eventos de OBRA ou PROJETO) — base 0038 + membership-check ----------
create or replace function public.cria_audit_log(
  p_tenant uuid, p_actor uuid, p_obra uuid, p_action text, p_entity_type text,
  p_entity_id uuid, p_changed jsonb, p_entity_label text,
  p_entity_seq bigint, p_actor_label text, p_projeto uuid)
returns void
language plpgsql security definer set search_path = '' as $$
declare
  v_uid    uuid := (select auth.uid());
  v_tenant uuid;
  v_label  text;
begin
  -- p_tenant/p_actor/p_actor_label IGNORADOS de propósito (derivar do contexto).
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;

  if p_obra is not null then
    -- A2: ator = membro ATIVO da obra.
    if p_obra not in (select public.current_obra_ids()) then
      raise exception 'sem permissao na obra do evento' using errcode = '42501';
    end if;
    select o.tenant_id into v_tenant from public.obras o where o.id = p_obra;
    if v_tenant is null then
      raise exception 'obra inexistente' using errcode = '23503';
    end if;
  elsif p_projeto is not null then
    -- A2: ator = membro ATIVO do projeto (arquiteto OU cliente — quem legitimamente gera o evento).
    if p_projeto not in (select public.current_projeto_ids()) then
      raise exception 'sem permissao no projeto do evento' using errcode = '42501';
    end if;
    select pj.tenant_id into v_tenant from public.projetos pj where pj.id = p_projeto;
    if v_tenant is null then
      raise exception 'projeto inexistente' using errcode = '23503';
    end if;
  else
    v_tenant := v_uid;
  end if;

  select coalesce(pr.nome, pr.email::text) into v_label
  from public.profiles pr where pr.id = v_uid;

  insert into public.audit_log
    (tenant_id, actor_id, obra_id, projeto_id, action, entity_type, entity_id, changed,
     entity_label, entity_seq, actor_label)
  values
    (v_tenant, v_uid, p_obra, p_projeto, p_action, p_entity_type, p_entity_id, p_changed,
     p_entity_label, p_entity_seq, v_label);
end;
$$;
alter function public.cria_audit_log(uuid,uuid,uuid,text,text,uuid,jsonb,text,bigint,text,uuid)
  owner to postgres;
revoke all on function public.cria_audit_log(uuid,uuid,uuid,text,text,uuid,jsonb,text,bigint,text,uuid)
  from public, anon;
grant execute on function public.cria_audit_log(uuid,uuid,uuid,text,text,uuid,jsonb,text,bigint,text,uuid)
  to authenticated;

commit;
