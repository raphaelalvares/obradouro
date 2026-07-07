-- 0110_export_reaper.sql  (Export DURÁVEL — reaper cross-tenant + cap de tentativas)
--
-- CONTEXTO: o export de dados (Fase 8; tabela export_jobs em 0051) roda o worker via FastAPI
-- BackgroundTasks — in-process, 1 worker uvicorn, DEPOIS da resposta. Se o processo reinicia/
-- deploya/cai/OOM antes ou durante o worker, o job fica ÓRFÃO em 'pendente'/'processando' PARA
-- SEMPRE: não havia reaper, retry nem cron (era o "na fila há 1 mês"). Esta migration dá a rede:
--   (1) coluna `tentativas`: o claim atômico do worker incrementa a cada pegada. Sem isso um
--       job-VENENO (que estoura a RAM e mata o worker toda vez) seria reprocessado em loop pelo
--       reaper e derrubaria a API inteira (worker único) para TODOS os tenants — pior que o bug.
--   (2) `export_jobs_reap(...)`: LISTA os jobs travados CROSS-TENANT. O reaper roda como cria_app
--       SEM contexto de RLS (não tem JWT), então precisa de uma função SECURITY DEFINER (owner
--       postgres) para enxergar além do próprio tenant — padrão do repo (0092, 0109). Devolve só
--       id + tenant_id; o reaper reidrata o contexto do tenant por-job para reprocessar.
--   (3) `export_jobs_falhar_excedidos(...)`: MARCA 'erro' os que estouraram o teto de tentativas.
--
-- Aplicar como postgres (SQL Editor / db push), DEPOIS do 0109 e ANTES do deploy do backend (o
-- reaper no lifespan chama estas funções). A conexão cria_app é não-owner.

begin;

-- =====================================================================================
-- (1) Contador de tentativas do worker (anti job-veneno). Nasce em 0 nos jobs já existentes.
-- =====================================================================================
alter table public.export_jobs
  add column if not exists tentativas int not null default 0;

-- =====================================================================================
-- (2) Jobs TRAVADOS, cross-tenant (SECURITY DEFINER: o reaper é cria_app sem JWT → sem esta função
--     o RLS de export_jobs esconderia todas as linhas). Um job é "travado" quando:
--       • 'pendente'    e parado há mais de p_pendente_seg   (o caminho feliz vira 'processando'
--                        em milissegundos; passou a graça ⇒ o dispatch inline nunca o pegou), OU
--       • 'processando' e parado há mais de p_processando_seg (o lease do worker; passou ⇒ o worker
--                        morreu no meio). `updated_at` é mantido pelo trigger set_updated_at.
--     Exclui os que já estouraram o teto (esses viram 'erro' por (3)). Só devolve id + tenant_id.
-- =====================================================================================
create or replace function public.export_jobs_reap(
  p_pendente_seg int, p_processando_seg int, p_max_tentativas int, p_limit int
)
returns table (id uuid, tenant_id uuid)
language sql stable security definer set search_path = '' as $$
  select j.id, j.tenant_id
  from public.export_jobs j
  where j.tentativas < p_max_tentativas
    and (
      (j.status = 'pendente'
         and j.updated_at < now() - make_interval(secs => p_pendente_seg))
      or
      (j.status = 'processando'
         and j.updated_at < now() - make_interval(secs => p_processando_seg))
    )
  order by j.created_at
  limit greatest(1, least(coalesce(p_limit, 20), 100));
$$;
alter function public.export_jobs_reap(int, int, int, int) owner to postgres;
revoke all on function public.export_jobs_reap(int, int, int, int) from public, anon, authenticated;
grant execute on function public.export_jobs_reap(int, int, int, int) to cria_app;

-- =====================================================================================
-- (3) Aposenta como 'erro' os jobs EXAUSTOS (tentativas >= teto) E TRAVADOS (mesma janela de
--     frescor do reap, sobre updated_at). O frescor é ESSENCIAL: sem ele, um job que chegou ao teto
--     na tentativa que está DANDO CERTO agora (ex.: re-POST "Tentar de novo") seria marcado 'erro'
--     no meio do montar_zip — e o _set_status('pronto') do worker, guardado por `status =
--     'processando'`, casaria 0 linhas → o .zip bom viraria órfão e o usuário veria 'erro'. Só
--     aposenta quem está exausto E parado (worker morto). Devolve quantos marcou. Definer (cross-tenant).
-- =====================================================================================
create or replace function public.export_jobs_falhar_excedidos(
  p_max_tentativas int, p_pendente_seg int, p_processando_seg int
)
returns integer
language plpgsql volatile security definer set search_path = '' as $$
declare v_n integer;
begin
  update public.export_jobs
     set status = 'erro',
         erro = 'excedeu o número de tentativas de geração'
   where tentativas >= p_max_tentativas
     and (
       (status = 'pendente'
          and updated_at < now() - make_interval(secs => p_pendente_seg))
       or
       (status = 'processando'
          and updated_at < now() - make_interval(secs => p_processando_seg))
     );
  get diagnostics v_n = row_count;
  return v_n;
end; $$;
alter function public.export_jobs_falhar_excedidos(int, int, int) owner to postgres;
revoke all on function public.export_jobs_falhar_excedidos(int, int, int)
  from public, anon, authenticated;
grant execute on function public.export_jobs_falhar_excedidos(int, int, int) to cria_app;

commit;
