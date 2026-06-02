-- 0010_rls_enable.sql  (Fase 1)
-- Habilita RLS nas tabelas multi-tenant.
-- ENABLE sem FORCE (decisão): cria_app NÃO é owner, então já fica 100% sujeita à RLS
-- (a 2ª camada vale). As funções SECURITY DEFINER (owner postgres) ignoram a RLS por
-- ISENÇÃO DE OWNER — sem depender de o postgres ter BYPASSRLS (incerto no Supabase).
-- (obra_seq_counters já foi habilitada no 0004.)

alter table public.profiles      enable row level security;
alter table public.obras         enable row level security;
alter table public.obra_membros  enable row level security;
alter table public.obra_codigos  enable row level security;
alter table public.audit_log     enable row level security;
