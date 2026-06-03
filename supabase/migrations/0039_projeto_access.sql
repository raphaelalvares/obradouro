-- 0039_projeto_access.sql  (Fase 5 — grants a cria_app + RLS das 7 tabelas + rótulo de pendentes)
-- cria_app é role NÃO-owner: sem grant explícito por tabela, todo acesso falha "permission denied".
-- Grants ASSIMÉTRICOS (espelham 0024/0030): revisao_arquivos SEM update (imutável); revisoes SEM
-- delete (prova de escopo; cascade do projeto limpa). RLS = 2ª camada; guards (0040) = regra fina.
-- Toda policy UPDATE traz USING **e** WITH CHECK (cinto-e-suspensório; impede a linha NOVA escapar
-- do escopo), como 0013/0014/0024.

grant select, insert, update, delete on public.projetos          to cria_app;
grant select, insert, update, delete on public.projeto_membros   to cria_app;
grant select, insert, update, delete on public.projeto_codigos   to cria_app;
grant select, insert, update          on public.revisoes          to cria_app;  -- sem delete (imutável)
grant select, insert, delete          on public.revisao_arquivos  to cria_app;  -- sem update (imutável)
grant select, insert, update, delete on public.moodboard_secoes  to cria_app;
grant select, insert, update, delete on public.moodboard_itens   to cria_app;

alter table public.projetos          enable row level security;
alter table public.projeto_membros   enable row level security;
alter table public.projeto_codigos   enable row level security;
alter table public.revisoes          enable row level security;
alter table public.revisao_arquivos  enable row level security;
alter table public.moodboard_secoes  enable row level security;
alter table public.moodboard_itens   enable row level security;

-- ===================== PROJETOS =====================
drop policy if exists projetos_select on public.projetos;
create policy projetos_select on public.projetos
  for select to authenticated
  using ( id in (select public.current_projeto_ids()) or tenant_id = (select auth.uid()) );
drop policy if exists projetos_insert on public.projetos;
create policy projetos_insert on public.projetos
  for insert to authenticated
  with check ( tenant_id = (select auth.uid()) );
drop policy if exists projetos_update on public.projetos;
create policy projetos_update on public.projetos
  for update to authenticated
  using      ( id in (select public.current_projeto_ids()) or tenant_id = (select auth.uid()) )
  with check ( id in (select public.current_projeto_ids()) or tenant_id = (select auth.uid()) );
drop policy if exists projetos_delete on public.projetos;
create policy projetos_delete on public.projetos
  for delete to authenticated
  using ( tenant_id = (select auth.uid()) );

-- ===================== PROJETO_MEMBROS (espelha 0014) =====================
drop policy if exists projeto_membros_select on public.projeto_membros;
create policy projeto_membros_select on public.projeto_membros
  for select to authenticated
  using ( projeto_id in (select public.current_projeto_ids()) or profile_id = (select auth.uid()) );
drop policy if exists projeto_membros_insert on public.projeto_membros;
create policy projeto_membros_insert on public.projeto_membros
  for insert to authenticated
  with check ( public.is_arquiteto_ativo_projeto(projeto_id) );
drop policy if exists projeto_membros_update on public.projeto_membros;
create policy projeto_membros_update on public.projeto_membros
  for update to authenticated
  using      ( projeto_id in (select public.current_projeto_ids()) or profile_id = (select auth.uid()) )
  with check ( projeto_id in (select public.current_projeto_ids()) or profile_id = (select auth.uid()) );
drop policy if exists projeto_membros_delete on public.projeto_membros;
create policy projeto_membros_delete on public.projeto_membros
  for delete to authenticated
  using ( projeto_id in (select public.current_projeto_ids()) );

-- ===================== PROJETO_CODIGOS (só arquiteto; resgatar é definer 0041) =====================
drop policy if exists projeto_codigos_select on public.projeto_codigos;
create policy projeto_codigos_select on public.projeto_codigos
  for select to authenticated
  using ( public.is_arquiteto_ativo_projeto(projeto_id) );
drop policy if exists projeto_codigos_insert on public.projeto_codigos;
create policy projeto_codigos_insert on public.projeto_codigos
  for insert to authenticated
  with check ( public.is_arquiteto_ativo_projeto(projeto_id) );
drop policy if exists projeto_codigos_update on public.projeto_codigos;
create policy projeto_codigos_update on public.projeto_codigos
  for update to authenticated
  using      ( public.is_arquiteto_ativo_projeto(projeto_id) )
  with check ( public.is_arquiteto_ativo_projeto(projeto_id) );

-- ===================== REVISOES =====================
drop policy if exists revisoes_select on public.revisoes;
create policy revisoes_select on public.revisoes
  for select to authenticated
  using ( projeto_id in (select public.current_projeto_ids()) );
drop policy if exists revisoes_insert on public.revisoes;
create policy revisoes_insert on public.revisoes
  for insert to authenticated
  with check ( public.is_arquiteto_ativo_projeto(projeto_id) );
-- UPDATE: membro ativo (cliente decide; guard 0040 refina coluna/papel/transição). USING + WITH CHECK.
drop policy if exists revisoes_update on public.revisoes;
create policy revisoes_update on public.revisoes
  for update to authenticated
  using      ( projeto_id in (select public.current_projeto_ids()) )
  with check ( projeto_id in (select public.current_projeto_ids()) );

-- ===================== REVISAO_ARQUIVOS (espelha anexos 0030; sem update) =====================
drop policy if exists revisao_arquivos_select on public.revisao_arquivos;
create policy revisao_arquivos_select on public.revisao_arquivos
  for select to authenticated
  using ( projeto_id in (select public.current_projeto_ids()) );
drop policy if exists revisao_arquivos_insert on public.revisao_arquivos;
create policy revisao_arquivos_insert on public.revisao_arquivos
  for insert to authenticated
  with check ( public.is_arquiteto_ativo_projeto(projeto_id) );
drop policy if exists revisao_arquivos_delete on public.revisao_arquivos;
create policy revisao_arquivos_delete on public.revisao_arquivos
  for delete to authenticated
  using ( public.is_arquiteto_ativo_projeto(projeto_id) );

-- ===================== MOODBOARD (arquiteto cura; cliente vê) =====================
drop policy if exists moodboard_secoes_select on public.moodboard_secoes;
create policy moodboard_secoes_select on public.moodboard_secoes
  for select to authenticated
  using ( projeto_id in (select public.current_projeto_ids()) );
drop policy if exists moodboard_secoes_insert on public.moodboard_secoes;
create policy moodboard_secoes_insert on public.moodboard_secoes
  for insert to authenticated
  with check ( public.is_arquiteto_ativo_projeto(projeto_id) );
drop policy if exists moodboard_secoes_update on public.moodboard_secoes;
create policy moodboard_secoes_update on public.moodboard_secoes
  for update to authenticated
  using      ( public.is_arquiteto_ativo_projeto(projeto_id) )
  with check ( public.is_arquiteto_ativo_projeto(projeto_id) );
drop policy if exists moodboard_secoes_delete on public.moodboard_secoes;
create policy moodboard_secoes_delete on public.moodboard_secoes
  for delete to authenticated
  using ( public.is_arquiteto_ativo_projeto(projeto_id) );

drop policy if exists moodboard_itens_select on public.moodboard_itens;
create policy moodboard_itens_select on public.moodboard_itens
  for select to authenticated
  using ( projeto_id in (select public.current_projeto_ids()) );
drop policy if exists moodboard_itens_insert on public.moodboard_itens;
create policy moodboard_itens_insert on public.moodboard_itens
  for insert to authenticated
  with check ( public.is_arquiteto_ativo_projeto(projeto_id) );
drop policy if exists moodboard_itens_update on public.moodboard_itens;
create policy moodboard_itens_update on public.moodboard_itens
  for update to authenticated
  using      ( public.is_arquiteto_ativo_projeto(projeto_id) )
  with check ( public.is_arquiteto_ativo_projeto(projeto_id) );
drop policy if exists moodboard_itens_delete on public.moodboard_itens;
create policy moodboard_itens_delete on public.moodboard_itens
  for delete to authenticated
  using ( public.is_arquiteto_ativo_projeto(projeto_id) );

-- ===================== Rótulo MAGRO de pendentes (espelha 0015) =====================
create or replace function public.minhas_inscricoes_projeto_pendentes()
returns table (projeto_id uuid, projeto_nome text, seq_humano bigint, invited_by_nome text)
language plpgsql stable security definer set search_path = '' as $$
begin
  return query
    select pj.id, pj.nome, pj.seq_humano, p.nome
    from public.projeto_membros pm
    join public.projetos pj on pj.id = pm.projeto_id
    left join public.profiles p on p.id = pm.invited_by
    where pm.profile_id = (select auth.uid())
      and pm.estado = 'pendente';
end;
$$;
alter function public.minhas_inscricoes_projeto_pendentes() owner to postgres;
revoke all on function public.minhas_inscricoes_projeto_pendentes() from public, anon;
grant execute on function public.minhas_inscricoes_projeto_pendentes() to authenticated;
