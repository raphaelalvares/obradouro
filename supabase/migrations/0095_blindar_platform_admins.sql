-- 0095_blindar_platform_admins.sql  (Blindagem da tabela de admins — defesa em profundidade)
--
-- Red-report (auditoria 2026-06-26): NÃO há hoje caminho explorável p/ um 'authenticated'/'anon' se
-- autoconceder admin — is_platform_admin() resolve só por auth.uid() contra platform_admins, nenhuma
-- RPC concedida ao app escreve profile_id, e toda função SECURITY DEFINER tem search_path travado.
-- PORÉM a proteção de platform_admins contra o role 'authenticated' dependia de UM único controle: a
-- RLS default-deny (RLS ligada, ZERO policy). Como o Supabase aplica por padrão
-- "alter default privileges ... grant all on tables to anon, authenticated", a tabela provavelmente
-- nasceu com GRANT ALL p/ authenticated; se alguém criar uma policy permissiva por engano (ou desligar
-- a RLS) numa migration futura, um logado leria/escreveria a tabela direto via PostgREST e viraria
-- admin. Este arquivo remove essa margem fina com 2 travas independentes:
--   (1) REVOKE explícito do privilégio de tabela p/ anon/authenticated/public — PostgREST nem expõe.
--   (2) Trigger de lockdown: aborta QUALQUER escrita por role de aplicação (authenticated/anon/
--       cria_app), mesmo que um GRANT/policy seja reintroduzido por engano. As escritas legítimas
--       (seed no apply e admin_marcar_vistos, ambas rodando como postgres) continuam passando.
--
-- NÃO usar "force row level security": forçaria a RLS também p/ o owner postgres, quebrando o seed e
-- as próprias funções SECURITY DEFINER (que leem a tabela como owner). revoke + trigger já fecham o
-- role de aplicação sem esse risco.
--
-- Aplicar como postgres (SQL Editor / db push), DEPOIS do 0094. Depende de 0090 (platform_admins).

begin;

-- (1) Tira o privilégio de tabela das roles de aplicação (não dependemos mais só da RLS no-policy).
--     As funções SECURITY DEFINER são owner=postgres → seguem lendo/escrevendo (owner ignora grants
--     e RLS). cria_app nunca toca a tabela direto, então não recebe nada.
revoke all on table public.platform_admins from anon, authenticated, public;

-- (2) Trava de escrita: só o owner (postgres) — no seed/apply OU DE DENTRO de uma função SECURITY
--     DEFINER (que roda como postgres) — pode escrever. Qualquer role de aplicação é abortada.
--     A função é SECURITY INVOKER de PROPÓSITO: assim current_user reflete o role REAL no momento da
--     escrita (postgres dentro de admin_marcar_vistos/seed; authenticated/anon/cria_app numa tentativa
--     direta). Se fosse SECURITY DEFINER, current_user seria sempre o owner e a trava nunca pegaria.
create or replace function public.platform_admins_lockdown()
returns trigger language plpgsql set search_path = '' as $$
begin
  if current_user in ('authenticated', 'anon', 'cria_app') then
    raise exception 'platform_admins: escrita bloqueada para role de aplicacao (%)', current_user
      using errcode = '42501';
  end if;
  return case when tg_op = 'DELETE' then old else new end;
end; $$;
alter function public.platform_admins_lockdown() owner to postgres;
revoke all on function public.platform_admins_lockdown() from public, anon;

drop trigger if exists trg_platform_admins_lockdown on public.platform_admins;
create trigger trg_platform_admins_lockdown
  before insert or update or delete on public.platform_admins
  for each row execute function public.platform_admins_lockdown();

commit;

-- =====================================================================================
-- VERIFICAÇÃO MANUAL pós-apply (rode no SQL Editor; deve confirmar a blindagem):
--   -- (a) nenhuma role de aplicação com privilégio de tabela:
--   select grantee, privilege_type from information_schema.role_table_grants
--    where table_schema = 'public' and table_name = 'platform_admins';
--   -- esperado: NÃO aparecer 'anon' nem 'authenticated'.
--   -- (b) RLS ligada e SEM policy:
--   select relrowsecurity from pg_class where oid = 'public.platform_admins'::regclass;  -- t
--   select count(*) from pg_policies where schemaname='public' and tablename='platform_admins'; -- 0
-- =====================================================================================
