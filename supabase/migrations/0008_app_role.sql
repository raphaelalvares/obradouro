-- 0008_app_role.sql  (Fase 1)
-- Role de aplicação DEDICADA usada pelo backend. NÃO é owner, NÃO tem BYPASSRLS:
-- por isso a RLS (2ª camada) vale de verdade no caminho da API.
-- (Reordenado vs design: a role é criada ANTES dos grants/revokes de audit_log em 0009.)

-- Cria a role de LOGIN sem senha aqui (não versionar senha no git).
-- >>> PASSO MANUAL OBRIGATÓRIO depois de aplicar: defina a senha (guardar como secret no EasyPanel):
--       alter role cria_app password '<SENHA_FORTE>';
-- E use essa senha no DATABASE_URL (usuário do pooler: cria_app.<project-ref>).
create role cria_app login;

-- Pode assumir o role 'authenticated' do Supabase (para a RLS e auth.uid()).
grant authenticated to cria_app;

grant usage on schema public to cria_app;

-- Tabelas multi-tenant: leitura/escrita (a RLS restringe por obra/tenant).
grant select, insert, update on
  public.profiles,
  public.obras,
  public.obra_membros,
  public.obra_codigos
  to cria_app;

-- audit_log: SOMENTE leitura direta. INSERT é via função SECURITY DEFINER (0009).
-- (sem update/delete/truncate — append-only).
grant select on public.audit_log to cria_app;

-- obra_seq_counters: NENHUM grant — só o trigger SECURITY DEFINER mexe.
