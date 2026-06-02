-- 0012_rls_profiles.sql  (Fase 1)
-- Cada um vê/edita o próprio perfil; e vê perfis de quem compartilha obra ATIVA
-- (para renderizar nomes de membros). (select auth.uid()) é cacheado via initPlan.

create policy profiles_select on public.profiles
  for select to authenticated
  using (
        id = (select auth.uid())
     or id in (
          select om.profile_id
          from public.obra_membros om
          where om.obra_id in (select public.current_obra_ids())
        )
  );

create policy profiles_update on public.profiles
  for update to authenticated
  using      ( id = (select auth.uid()) )
  with check ( id = (select auth.uid()) );

-- UPSERT do próprio perfil pelo backend (após Admin API criar o auth.user).
create policy profiles_insert on public.profiles
  for insert to authenticated
  with check ( id = (select auth.uid()) );
