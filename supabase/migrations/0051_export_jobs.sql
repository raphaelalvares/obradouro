-- 0051_export_jobs.sql  (Fase 8 — engine de export "em camadas" / portabilidade LGPD)
-- O arquiteto pede um export → job ASSÍNCRONO empacota um .zip (fotos por obra + CSV legível) no
-- storage (módulo da Fase 4) → fica disponível por 30 dias → expurgo REAL (apaga do storage). O job
-- roda em background com o MESMO contexto RLS do tenant (lê só os dados dele). Aqui só o registro do
-- job; os bytes do .zip vivem no storage (não no banco). Sem seq humano (ação de servidor, não
-- entidade de obra). O gatilho "cancelou a conta → offboarding automático" entra na Fase 9 (cobrança),
-- de onde nasce o cancelamento; esta engine já serve à portabilidade LGPD (titular pode levar os dados).

create table if not exists public.export_jobs (
  id            uuid        primary key,
  tenant_id     uuid        not null references public.profiles(id) on delete cascade,
  status        text        not null default 'pendente'
                  check (status in ('pendente', 'processando', 'pronto', 'erro', 'expirado')),
  zip_key       text,                 -- chave opaca no storage (NULL até ficar pronto / após expurgo)
  tamanho_bytes bigint,
  erro          text,
  pronto_em     timestamptz,
  expira_em     timestamptz,          -- pronto_em + 30 dias; após isso o .zip é expurgado
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index if not exists ix_export_jobs_tenant on public.export_jobs (tenant_id, created_at desc);
drop trigger if exists trg_export_jobs_updated_at on public.export_jobs;
create trigger trg_export_jobs_updated_at
  before update on public.export_jobs for each row execute function public.set_updated_at();

grant select, insert, update, delete on public.export_jobs to cria_app;
alter table public.export_jobs enable row level security;

-- Self: cada arquiteto só vê/cria/atualiza/apaga os PRÓPRIOS jobs. O worker em background usa o
-- contexto RLS do mesmo tenant, então enxerga e atualiza o próprio job sem exceção de owner.
-- Expurgo = UPDATE para status 'expirado' (mantém o registro; só zera zip_key e apaga os bytes).
drop policy if exists export_jobs_select on public.export_jobs;
create policy export_jobs_select on public.export_jobs
  for select to authenticated using ( tenant_id = (select auth.uid()) );

drop policy if exists export_jobs_insert on public.export_jobs;
create policy export_jobs_insert on public.export_jobs
  for insert to authenticated with check ( tenant_id = (select auth.uid()) );

drop policy if exists export_jobs_update on public.export_jobs;
create policy export_jobs_update on public.export_jobs
  for update to authenticated
  using      ( tenant_id = (select auth.uid()) )
  with check ( tenant_id = (select auth.uid()) );

drop policy if exists export_jobs_delete on public.export_jobs;
create policy export_jobs_delete on public.export_jobs
  for delete to authenticated using ( tenant_id = (select auth.uid()) );
