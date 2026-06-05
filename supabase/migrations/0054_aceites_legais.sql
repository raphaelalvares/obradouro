-- 0054_aceites_legais.sql  (Cadastro/OAuth — aceite versionado de Termos/Privacidade)
-- Prova de aceite dos documentos legais: quem (profile), qual documento, qual versão, quando e a
-- origem (cadastro/oauth/login). IMUTÁVEL: sem update/delete (a prova não muda). Re-aceite = nova
-- linha quando a versão vigente muda (a versão é carimbada pelo backend — app/core/legal.py).
-- Trilha jurídica: "aceite do arquiteto no cadastro" com prova versionada.
-- Aplicar como postgres. DEV antes de PROD.

create table if not exists public.aceites_legais (
  id          uuid        primary key default gen_random_uuid(),
  profile_id  uuid        not null references public.profiles(id) on delete cascade,
  documento   text        not null,   -- 'termos' | 'privacidade'
  versao      text        not null,   -- ex.: '2026-06-04' (versão vigente carimbada pelo backend)
  origem      text,                   -- 'cadastro' (atestado no metadata) | 'gate' (aceite no app)
  aceito_em   timestamptz not null default now(),
  unique (profile_id, documento, versao)
);
create index if not exists ix_aceites_legais_profile on public.aceites_legais (profile_id);

grant select, insert on public.aceites_legais to cria_app;
alter table public.aceites_legais enable row level security;

-- Self: cada um lê e registra apenas os próprios aceites. Sem policy de update/delete (prova imutável).
drop policy if exists aceites_legais_select on public.aceites_legais;
create policy aceites_legais_select on public.aceites_legais
  for select to authenticated using ( profile_id = (select auth.uid()) );

drop policy if exists aceites_legais_insert on public.aceites_legais;
create policy aceites_legais_insert on public.aceites_legais
  for insert to authenticated with check ( profile_id = (select auth.uid()) );
