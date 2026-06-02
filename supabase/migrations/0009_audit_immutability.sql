-- 0009_audit_immutability.sql  (Fase 1)
-- Append-only do audit_log em 3 camadas: privilégio + trigger + (RLS default-deny em 0017).

-- 1) Privilégio: cria_app não pode mutar (defensivo; já não foi concedido em 0008).
revoke insert, update, delete, truncate on public.audit_log from cria_app;
grant  select on public.audit_log to cria_app;

-- 2) Trigger que bloqueia update/delete (protege contra grant vazado numa migration futura).
create or replace function public.audit_log_block_mutation()
returns trigger
language plpgsql
as $$
begin
  raise exception 'audit_log e append-only: % nao permitido', tg_op
    using errcode = '0A000';   -- feature_not_supported
end;
$$;

create trigger trg_audit_no_update
  before update on public.audit_log
  for each row execute function public.audit_log_block_mutation();

create trigger trg_audit_no_delete
  before delete on public.audit_log
  for each row execute function public.audit_log_block_mutation();

-- 3) Caminho de escrita ÚNICO (SECURITY DEFINER, owner postgres → grava por isenção de owner).
create or replace function public.cria_audit_log(
  p_tenant uuid, p_actor uuid, p_obra uuid, p_action text, p_entity_type text,
  p_entity_id uuid, p_changed jsonb, p_entity_label text,
  p_entity_seq bigint, p_actor_label text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.audit_log
    (tenant_id, actor_id, obra_id, action, entity_type, entity_id, changed,
     entity_label, entity_seq, actor_label)
  values
    (p_tenant, p_actor, p_obra, p_action, p_entity_type, p_entity_id, p_changed,
     p_entity_label, p_entity_seq, p_actor_label);
end;
$$;

alter function public.cria_audit_log(uuid,uuid,uuid,text,text,uuid,jsonb,text,bigint,text)
  owner to postgres;
revoke all on function public.cria_audit_log(uuid,uuid,uuid,text,text,uuid,jsonb,text,bigint,text)
  from public, anon;
grant execute on function public.cria_audit_log(uuid,uuid,uuid,text,text,uuid,jsonb,text,bigint,text)
  to authenticated;
