-- 0038_audit_projeto.sql  (Fase 5 — CORE: audit do projeto visível ao arquiteto E ao cliente)
-- Achado adversarial CRÍTICO: todo evento de projeto tem obra_id NULL; a policy audit_select (0017)
-- só liberava eventos sem obra via `tenant_id = auth.uid()` (= ARQUITETO). O CLIENTE — que é o ATOR
-- de aprovar/recusar/pedir-alteração (a "prova de escopo") — NUNCA veria o histórico, e
-- GET /projetos/{id}/audit voltaria VAZIO sem erro. Correção: coluna projeto_id denormalizada no
-- audit_log + sobrecarga de 11 args de cria_audit_log que a carimba e DERIVA o tenant do PROJETO +
-- ramo `projeto_id in current_projeto_ids()` na policy (espelha o ramo de obra; vale p/ ambos).

-- (1) coluna + índice (espelha ix_audit_obra). add column if not exists => re-aplicável; não fere
-- o append-only (linhas não são mutadas, só o schema ganha coluna nullable).
alter table public.audit_log add column if not exists projeto_id uuid;
create index if not exists ix_audit_projeto on public.audit_log (projeto_id);

-- (2) SOBRECARGA de 11 args (NÃO altera a de 10 args usada por obra/checklist/anexos). Deriva tenant:
-- obra (se houver) > projeto (se houver) > ator. Carimba projeto_id. Ator/label do contexto (nunca
-- confiar no chamador, igual 0019). Eventos de projeto SEM obra ficam com tenant=arquiteto e
-- projeto_id setado → arquiteto vê pelo tenant, cliente vê pelo ramo de projeto da policy.
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
    select o.tenant_id into v_tenant from public.obras o where o.id = p_obra;
    if v_tenant is null then
      raise exception 'obra inexistente' using errcode = '23503';
    end if;
  elsif p_projeto is not null then
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

-- (3) Policy de leitura: adiciona o ramo de projeto (membro ATIVO vê — arquiteto E cliente).
drop policy if exists audit_select on public.audit_log;
create policy audit_select on public.audit_log
  for select to authenticated
  using (
        obra_id in (select public.current_obra_ids())
     or projeto_id in (select public.current_projeto_ids())
     or (obra_id is null and projeto_id is null and tenant_id = (select auth.uid()))
  );
