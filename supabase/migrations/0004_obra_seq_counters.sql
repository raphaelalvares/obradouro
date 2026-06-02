-- 0004_obra_seq_counters.sql  (Fase 1)
-- Contador de seq_humano por tenant. Ninguém escreve direto: só o trigger
-- assign_obra_seq (SECURITY DEFINER, owner postgres) em 0005.

create table public.obra_seq_counters (
  tenant_id uuid   primary key references public.profiles(id) on delete cascade,
  last_seq  bigint not null default 0
);

-- RLS habilitada SEM policy: cria_app (não-owner) fica negado por default.
-- NOTA: usamos ENABLE sem FORCE — assim a função SECURITY DEFINER (owner postgres)
-- escreve por ISENÇÃO DE OWNER, sem depender de o postgres ter BYPASSRLS.
alter table public.obra_seq_counters enable row level security;
