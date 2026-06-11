-- 0074_sec_m1_obras_update_arquiteto.sql  (SEGURANÇA — Fase 2, item M1 / ALTO)
--
-- BUG (red-report Fase 1, M1 — CONFIRMADO explorável direto): a policy `obras_update` (0013) era
-- `using/with check (id in current_obra_ids())` → QUALQUER membro ativo (cliente/prestador) podia dar
-- UPDATE em obras: renomear, mudar datas e, principalmente, mudar `status`. Como a RLS é a única
-- fronteira (authenticated tem DML por default-priv), isso era explorável direto via
-- PATCH /rest/v1/obras: (a) cliente/prestador altera/sabota a obra; (b) qualquer um seta
-- `status='ativa'` direto, PULANDO a checagem de quota (_checar_vaga_obra_ativa só roda em
-- criar_obra/reativar_obra) → bypass de monetização.
--
-- CORREÇÃO:
--  (1) UPDATE restrito a ARQUITETO ativo (RLS) — fecha (a). Todos os caminhos legítimos de UPDATE são
--      arquiteto (rename/set_datas/arquivar em obras.py; aplicar_cronograma em checklist.py — todos
--      via obra_writable). Reativar usa a RPC reativar_obra (SECURITY DEFINER, isenta de RLS).
--  (2) Guard obras_guard (substitui obras_lock_tenant, que só travava tenant_id): identidade imutável
--      (id/tenant_id/seq_humano/created_at) + reativação (status→'ativa') SÓ pela RPC reativar_obra —
--      fecha (b). A RPC roda como owner postgres → current_user='postgres'; um UPDATE direto de
--      authenticated/anon tem current_user='authenticated' → bloqueado. Arquivar (status→'arquivada')
--      direto continua permitido (libera vaga, não consome).
--
-- NÃO QUEBRA NENHUM FLUXO (verificado caminho a caminho):
--   - rename_obra / set_datas / aplicar_cronograma: obra_writable (arquiteto) → policy passa; não
--     mexem em status → guard não dispara.
--   - set_status arquivar: arquiteto, status→'arquivada' (direto) → guard permite.
--   - set_status reativar: reativar_obra (RPC definer, owner postgres) → isenta da RLS; o guard vê
--     current_user='postgres' → permite o status→'ativa' (após a checagem de quota dentro da RPC).
--   - criar_obra: INSERT (definer) com status default 'ativa' → o guard é BEFORE UPDATE, não dispara.
--
-- Aplicar como postgres, DEPOIS da 0013, 0019 e 0021. DEV antes de PROD.
--
-- VERIFICAR após aplicar:
--   -- (1) policy de UPDATE agora exige arquiteto:
--   select policyname, qual, with_check from pg_policies
--   where schemaname='public' and tablename='obras' and cmd='UPDATE';
--   -- (2) regressão: arquiteto renomeia / muda datas / arquiva / reativa (via API) normalmente.
--   -- (3) ataque negado: como cliente/prestador, UPDATE direto de obras → 42501; como qualquer um,
--   --     UPDATE direto setando status='ativa' → 42501 (reativação deve usar reativar_obra).

begin;

-- (1) UPDATE só por arquiteto ativo.
drop policy if exists obras_update on public.obras;
create policy obras_update on public.obras
  for update to authenticated
  using      ( public.is_arquiteto_ativo(id) )
  with check ( public.is_arquiteto_ativo(id) );

-- (2) Guard: identidade imutável + reativação só pela RPC (substitui obras_lock_tenant).
create or replace function public.obras_guard()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  -- identidade/seq imutáveis (tenant_id já era travado em 0019; reforça id/seq_humano/created_at).
  if new.id is distinct from old.id
     or new.tenant_id is distinct from old.tenant_id
     or new.seq_humano is distinct from old.seq_humano
     or new.created_at is distinct from old.created_at then
    raise exception 'identidade da obra e imutavel' using errcode = '42501';
  end if;
  -- M1: status -> 'ativa' consome vaga do plano; SÓ pela RPC reativar_obra (owner postgres ->
  -- current_user='postgres', que roda _checar_vaga_obra_ativa). UPDATE direto (authenticated/anon)
  -- é bloqueado p/ não pular a quota. Arquivar (-> 'arquivada') direto continua permitido.
  if new.status = 'ativa'::public.status_obra
     and old.status is distinct from 'ativa'::public.status_obra
     and current_user <> 'postgres' then
    raise exception 'reativacao deve usar reativar_obra (checa o limite do plano)'
      using errcode = '42501';
  end if;
  return new;
end;
$$;
alter function public.obras_guard() owner to postgres;

drop trigger if exists trg_obras_lock_tenant on public.obras;
drop trigger if exists trg_obras_guard on public.obras;
create trigger trg_obras_guard
  before update on public.obras
  for each row execute function public.obras_guard();

-- limpa a função antiga (substituída por obras_guard); sem dependências após dropar o trigger.
drop function if exists public.obras_lock_tenant();

commit;
