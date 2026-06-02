-- 0014_rls_obra_membros.sql  (Fase 1)
-- Leitura via current_obra_ids() (SECURITY DEFINER) evita a recursão clássica.
-- Vê membros das obras onde é ativo OU a própria linha (inclusive PENDENTE, para aceitar).
-- A regra fina (só arquiteto adiciona/remove; pessoa só muda o próprio estado) é da API (camada 1).

create policy obra_membros_select on public.obra_membros
  for select to authenticated
  using (
        obra_id in (select public.current_obra_ids())
     or profile_id = (select auth.uid())
  );

create policy obra_membros_insert on public.obra_membros
  for insert to authenticated
  with check ( obra_id in (select public.current_obra_ids()) );

create policy obra_membros_update on public.obra_membros
  for update to authenticated
  using (
        obra_id in (select public.current_obra_ids())   -- arquiteto ativo da obra
     or profile_id = (select auth.uid())                 -- a própria pessoa (aceitar convite)
  )
  with check (
        obra_id in (select public.current_obra_ids())
     or profile_id = (select auth.uid())
  );

-- Remoção: coarse na RLS (membro ativo da obra); a regra fina (só arquiteto remove,
-- não remover o último arquiteto) é validada na API (camada 1).
create policy obra_membros_delete on public.obra_membros
  for delete to authenticated
  using ( obra_id in (select public.current_obra_ids()) );

-- O primeiro vínculo (criador→arquiteto) é criado pela função criar_obra (0018, definer).
