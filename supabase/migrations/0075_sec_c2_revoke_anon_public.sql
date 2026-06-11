-- 0075_sec_c2_revoke_anon_public.sql  (SEGURANÇA — Fase 2, item C2 / hardening sistêmico)
--
-- ACHADO (verificação externa de privilégios): por DEFAULT PRIVILEGES do Supabase (definidor postgres
-- e supabase_admin), TODA tabela/sequence/função criada no schema public nasce com acesso concedido a
-- `anon` E `authenticated` (anon=arwdDxtm). A premissa "grants só p/ cria_app" era falsa. Com isso, a
-- RLS é a ÚNICA fronteira no banco. Para `authenticated` NÃO há atalho (o backend opera como
-- `authenticated` via SET LOCAL ROLE — revogar quebraria o app; a RLS segura, e os furos foram
-- fechados em 0072-0074). Para `anon`, porém, NÃO há uso legítimo nenhum:
--   - o front usa o Supabase só para AUTH (supabase.auth.*); ZERO supabase.from()/rpc()/storage()
--     (confirmado) → todo dado vai pela API (FastAPI, como authenticated);
--   - signup cria o profile via handle_new_user (SECURITY DEFINER owner postgres), não como anon;
--   - as RPCs sensíveis já revogavam anon explicitamente; planos/tenant_assinaturas/seq_counters têm
--     0 policies (default-deny).
-- Hoje anon só está barrado pelo default-deny das policies `to authenticated` (anon não casa nenhuma).
-- Defesa-em-profundidade: REMOVER `anon` do schema public — fecha a superfície NÃO-AUTENTICADA de vez
-- (qualquer policy futura `to anon`/`to public` ou tabela sem policy deixa de ser alcançável por anon).
--
-- ESCOPO: mexe SÓ em `anon`. NÃO toca `authenticated` (o backend precisa do DML; a RLS é a fronteira).
-- NÃO revoga USAGE do schema (anon mantém USAGE; sem grants de objeto, USAGE sozinho não dá nada — e
-- evita efeitos colaterais no PostgREST/authenticator).
--
-- Aplicar como postgres, ao final da cadeia (não depende de ordem específica). DEV antes de PROD.
-- Idempotente (REVOKE do que já não há é no-op).
-- OBS p/ o futuro: se algum dia existir página pública lendo dados via PostgREST como anon, seria
-- preciso re-conceder + policy `to anon` explícita — mas o padrão da casa é API-only, então não deve.
--
-- VERIFICAR após aplicar:
--   -- anon deve sumir; authenticated permanece (necessário ao backend):
--   select grantee, count(*) as tabelas from information_schema.role_table_grants
--   where table_schema='public' and grantee in ('anon','authenticated') group by grantee;

begin;

-- (1) Objetos EXISTENTES: remove anon de tudo no public (tabelas, sequences, funções).
revoke all on all tables    in schema public from anon;
revoke all on all sequences in schema public from anon;
revoke all on all functions in schema public from anon;

-- (2) Objetos FUTUROS criados por postgres (as migrations rodam como postgres): não conceder a anon.
--     authenticated continua herdando o default (o backend precisa) — não é tocado aqui.
alter default privileges for role postgres in schema public revoke all on tables    from anon;
alter default privileges for role postgres in schema public revoke all on sequences from anon;
alter default privileges for role postgres in schema public revoke all on functions from anon;

commit;

-- NOTA (verificação manual, fora desta migration): existe também um DEFAULT PRIVILEGE com definidor
-- `supabase_admin` para o schema public concedendo a anon. Tabelas do APP são criadas por postgres
-- (corrigido acima); o default de supabase_admin só afeta objetos criados por supabase_admin (raros
-- em public). Alterá-lo exige privilégio sobre supabase_admin — conferir no Dashboard se necessário.
