-- 0070_sec_a1_cobranca_set_customer_self.sql  (SEGURANÇA — Fase 2, item A1 / ALTO)
--
-- BUG (red-report Fase 1, A1): public.cobranca_set_customer(p_tenant, p_customer) é SECURITY DEFINER,
-- grava o stripe_customer_id do p_tenant que vier no ARGUMENTO, sem checar o chamador, e está
-- concedida a `authenticated` (0052:40). Via PostgREST direto (Path B), um usuário chamava
-- POST /rest/v1/rpc/cobranca_set_customer com p_tenant=<uid da vítima> e sobrescrevia/sequestrava o
-- customer do Stripe de outro tenant (corrompe a conciliação e o checkout alheio).
--
-- POR QUE NÃO revogar de `authenticated` (como no C1): o ÚNICO chamador legítimo é o checkout
-- autenticado (app/services/cobranca.py:_customer_id), que roda DENTRO da request com
-- `SET LOCAL ROLE authenticated`. Revogar quebraria o checkout. (O webhook NÃO chama esta função —
-- chama cobranca_aplicar, tratada no C1.)
--
-- CORREÇÃO: a identidade passa a vir de auth.uid(), não do argumento. A função recusa quando
-- p_tenant != auth.uid(). No checkout legítimo, _customer_id passa p_tenant = user_id = auth.uid()
-- (mesma pessoa) → passa. Um atacante via Path B tem auth.uid() = ele mesmo (o JWT é dele), logo só
-- conseguiria gravar o PRÓPRIO customer — não o de terceiros. Mantém o grant a `authenticated`.
--   - errcode 42501 (insufficient_privilege): o backend mapeia 42501→403 (services/common._map_42501),
--     então, se algum dia disparar pela API, vira 403 limpo (não 500). Para legítimos nunca dispara.
--   - `is distinct from`: trata auth.uid() NULL (contexto sem JWT) como diferente → também recusa
--     (não há chamador cria_app/webhook desta função hoje; se um dia houver, ajustar em migration nova).
--
-- Mantém SECURITY DEFINER + search_path='' (anti-hijack) e reafirma owner/grants (CREATE OR REPLACE
-- preserva ACL, mas reafirmamos p/ a migration ser autossuficiente). Aplicar como postgres, DEPOIS da
-- 0052. DEV antes de PROD.
--
-- VERIFICAR após aplicar:
--   -- (1) o grant a authenticated CONTINUA (necessário p/ o checkout):
--   select grantee, privilege_type from information_schema.role_routine_grants
--   where routine_schema='public' and routine_name='cobranca_set_customer';
--   -- (2) chamada cruzada é negada: como um usuário A, tentar gravar o customer de um tenant B
--   --     (p_tenant = uid de B) deve abortar com 42501; com p_tenant = uid de A deve funcionar.

begin;

create or replace function public.cobranca_set_customer(p_tenant uuid, p_customer text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  -- A1: a identidade vem de auth.uid(), nunca do argumento (anti-forja cross-tenant via Path B).
  if p_tenant is distinct from auth.uid() then
    raise exception
      'cobranca_set_customer: p_tenant (%) deve ser o proprio tenant autenticado', p_tenant
      using errcode = 'insufficient_privilege';
  end if;

  insert into public.tenant_cobranca (tenant_id, stripe_customer_id)
  values (p_tenant, p_customer)
  on conflict (tenant_id) do update set stripe_customer_id = excluded.stripe_customer_id;
end; $$;

alter function public.cobranca_set_customer(uuid, text) owner to postgres;
revoke all on function public.cobranca_set_customer(uuid, text) from public, anon;
grant execute on function public.cobranca_set_customer(uuid, text) to authenticated, cria_app;

commit;
