-- 0019_hardening_fase1.sql  (Fase 1 — hardening pós-revisão adversarial)
-- Fecha buracos de defesa-em-profundidade encontrados na revisão. Aplicar DEV → PROD.

-- =====================================================================
-- (1) HIGH: cria_audit_log não pode confiar nos argumentos de IDENTIDADE.
-- Mantém a MESMA assinatura (zero mudança no backend), mas IGNORA p_tenant/p_actor/
-- p_actor_label e DERIVA tudo do contexto: ator = auth.uid(), tenant = dono da obra,
-- actor_label = perfil do ator. Fecha forja de ator/tenant e o actor_label nulo.
-- =====================================================================
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

-- =====================================================================
-- (2) MEDIUM: RLS de obra_membros permitia escalonar papel/trocar profile_id na 2ª camada.
-- Função de apoio + policy de INSERT restrita + trigger que tranca papel/profile_id.
-- =====================================================================
create or replace function public.is_arquiteto_ativo(p_obra uuid)
returns boolean
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  return exists (
    select 1 from public.obra_membros m
    where m.obra_id = p_obra
      and m.profile_id = (select auth.uid())
      and m.papel = 'arquiteto'
      and m.estado = 'ativo'
  );
end;
$$;
alter function public.is_arquiteto_ativo(uuid) owner to postgres;
revoke all on function public.is_arquiteto_ativo(uuid) from public, anon;
grant execute on function public.is_arquiteto_ativo(uuid) to authenticated;

-- INSERT só por arquiteto ativo (criar_obra/resgatar são SECURITY DEFINER → isentos, seguem ok)
drop policy if exists obra_membros_insert on public.obra_membros;
create policy obra_membros_insert on public.obra_membros
  for insert to authenticated
  with check ( public.is_arquiteto_ativo(obra_id) );

-- Trigger: não-arquiteto não pode mudar papel nem profile_id (o aceite só muda estado).
create or replace function public.obra_membros_guard()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if (new.papel is distinct from old.papel
      or new.profile_id is distinct from old.profile_id
      or new.obra_id is distinct from old.obra_id)
     and not public.is_arquiteto_ativo(old.obra_id) then
    raise exception 'apenas arquiteto pode alterar papel/membro' using errcode = '42501';
  end if;
  return new;
end;
$$;
alter function public.obra_membros_guard() owner to postgres;

drop trigger if exists trg_obra_membros_guard on public.obra_membros;
create trigger trg_obra_membros_guard
  before update on public.obra_membros
  for each row execute function public.obra_membros_guard();

-- =====================================================================
-- (3) LOW: tenant_id da obra é imutável (impede sequestro via UPDATE na 2ª camada).
-- =====================================================================
create or replace function public.obras_lock_tenant()
returns trigger
language plpgsql
as $$
begin
  if new.tenant_id is distinct from old.tenant_id then
    raise exception 'tenant_id da obra e imutavel' using errcode = '42501';
  end if;
  return new;
end;
$$;

drop trigger if exists trg_obras_lock_tenant on public.obras;
create trigger trg_obras_lock_tenant
  before update on public.obras
  for each row execute function public.obras_lock_tenant();
