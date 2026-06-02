-- 0017_rls_audit.sql  (Fase 1)
-- audit_log: só SELECT, por obra/tenant. INSERT só via cria_audit_log (0009).
-- Sem policy de INSERT/UPDATE/DELETE → default DENY reforça o append-only.

create policy audit_select on public.audit_log
  for select to authenticated
  using (
        obra_id in (select public.current_obra_ids())
     or (obra_id is null and tenant_id = (select auth.uid()))  -- eventos sem obra do próprio tenant
  );
