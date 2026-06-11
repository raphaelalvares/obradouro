-- 0069_sec_c1_revoke_cobranca_aplicar.sql  (SEGURANÇA — Fase 2, item C1 / CRÍTICO)
--
-- BUG (red-report Fase 1, C1): a função public.cobranca_aplicar(...) é SECURITY DEFINER, recebe
-- p_tenant/p_plano como ARGUMENTOS e NÃO deriva nada de auth.uid() nem valida o chamador. No 0052
-- ela foi concedida a `authenticated` ALÉM de `cria_app` (a intenção, no comentário do 0052:44, era
-- conceder SÓ ao webhook). Com o schema `public` exposto no PostgREST (padrão Supabase), qualquer
-- usuário autenticado podia chamar  POST /rest/v1/rpc/cobranca_aplicar  com p_tenant=<seu uid> e
-- p_plano='pro' e VIRAR PRO DE GRAÇA (obras ilimitadas, export_pdf, logo) sem passar pelo Stripe; ou,
-- com p_tenant=<uid da vítima>, adulterar/derrubar o billing de outro tenant.
--
-- CORREÇÃO (mínima e isolada): revogar EXECUTE de `authenticated`. O único chamador legítimo é o
-- WEBHOOK do Stripe (app/services/cobranca.py:processar_webhook), que abre a sessão por SessionLocal()
-- SEM `SET LOCAL ROLE authenticated` → roda como a role de login `cria_app`. O grant a `cria_app` é
-- EXPLÍCITO no 0052 (`to authenticated, cria_app`) e independe da herança de `authenticated`, então o
-- webhook continua funcionando. `public`/`anon` já estavam revogados no 0052.
--
-- POR QUE NÃO um simples revoke nos itens A1/A2 (vêm em migrations próprias): cobranca_set_customer
-- (checkout) e cria_audit_log (auditoria) são chamados DENTRO de uma request, onde o backend faz
-- `SET LOCAL ROLE authenticated` — revogar de `authenticated` quebraria esses caminhos. Lá a correção
-- é validar a identidade DENTRO da função (mantendo o grant). Aqui (C1), como o caminho legítimo é
-- `cria_app`, o revoke é a correção correta e completa.
--
-- NÃO REGREDIR: nunca reconceder cobranca_aplicar a `authenticated`. Aplicar como postgres (dono),
-- DEPOIS da 0052. DEV antes de PROD. Idempotente (revoke do que já não existe é no-op).
--
-- VERIFICAR após aplicar (deve listar só cria_app, NÃO authenticated):
--   select grantee, privilege_type
--   from information_schema.role_routine_grants
--   where routine_schema='public' and routine_name='cobranca_aplicar';

begin;

revoke execute on function
  public.cobranca_aplicar(uuid, text, text, text, timestamptz, text)
  from authenticated;

commit;
