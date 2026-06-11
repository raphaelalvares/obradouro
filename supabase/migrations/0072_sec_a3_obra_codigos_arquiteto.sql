-- 0072_sec_a3_obra_codigos_arquiteto.sql  (SEGURANÇA — Fase 2, item A3 / CRÍTICO)
--
-- BUG (red-report Fase 1, A3 — CONFIRMADO explorável direto pela verificação de privilégios):
-- a policy `obra_codigos_all` (0016) é `FOR ALL ... using/with check (obra_id in current_obra_ids())`,
-- ou seja, QUALQUER membro ATIVO da obra (inclusive cliente/prestador) podia INSERT um código de
-- convite com papel='arquiteto'. Como o Supabase concede DML em todas as tabelas a `authenticated`
-- (default privileges) e a RLS é a ÚNICA fronteira, isso é explorável DIRETO via
-- POST /rest/v1/obra_codigos: o atacante cria um código arquiteto, resgata numa 2ª conta
-- (resgatar_codigo_obra cria o vínculo) e, aceitando, VIRA ARQUITETO da obra de outro → escalada de
-- privilégio / sequestro. O lado PROJETO já estava correto (projeto_codigos_insert exige
-- is_arquiteto_ativo_projeto); esta migration espelha esse padrão no lado OBRA.
--
-- CORREÇÃO: dropar a policy ALL e criar SELECT/INSERT/UPDATE restritas a arquiteto ATIVO da obra
-- (public.is_arquiteto_ativo(obra_id)). Sem policy de DELETE (a API revoga via UPDATE set revoked_at,
-- nunca DELETE → fica default-deny, mais restrito).
--
-- NÃO QUEBRA NENHUM FLUXO (verificado):
--   - gerar_codigo / revogar_codigo / get_codigo_ativo (codigo.py): gateados por obra_writable
--     (arquiteto ativo) e rodam como `authenticated` → is_arquiteto_ativo(obra_id) = true → passam
--     (INSERT, UPDATE revoked_at, SELECT).
--   - resgatar_codigo_obra (0018, SECURITY DEFINER owner postgres): LÊ obra_codigos com isenção de
--     owner (RLS não se aplica ao owner; a tabela não é FORCE) → o resgate por quem-ainda-não-é-membro
--     continua funcionando, independentemente da policy de SELECT.
--
-- Aplicar como postgres, DEPOIS da 0016 e da 0019 (que define is_arquiteto_ativo). DEV antes de PROD.
--
-- VERIFICAR após aplicar:
--   -- (1) policies novas no lugar da antiga:
--   select policyname, cmd, qual, with_check from pg_policies
--   where schemaname='public' and tablename='obra_codigos' order by cmd;
--   -- (2) ataque negado: como cliente/prestador ATIVO de uma obra, um INSERT direto em obra_codigos
--   --     (papel='arquiteto') deve ser barrado pela RLS; como arquiteto, gerar/ver/revogar continua.

begin;

drop policy if exists obra_codigos_all on public.obra_codigos;

create policy obra_codigos_select on public.obra_codigos
  for select to authenticated
  using ( public.is_arquiteto_ativo(obra_id) );

create policy obra_codigos_insert on public.obra_codigos
  for insert to authenticated
  with check ( public.is_arquiteto_ativo(obra_id) );

create policy obra_codigos_update on public.obra_codigos
  for update to authenticated
  using      ( public.is_arquiteto_ativo(obra_id) )
  with check ( public.is_arquiteto_ativo(obra_id) );

commit;
