-- 0013_rls_obras.sql  (Fase 1)
-- Só obra onde você é membro ATIVO aparece. Pendente não enxerga a obra por aqui
-- (current_obra_ids filtra estado='ativo') — só o rótulo magro do 0015.

create policy obras_select on public.obras
  for select to authenticated
  using ( id in (select public.current_obra_ids()) );

-- Criação direta é restrita ao próprio tenant; a criação atômica (obra + vínculo
-- arquiteto) é feita pela função criar_obra (0018). Esta policy é defesa em profundidade.
create policy obras_insert on public.obras
  for insert to authenticated
  with check ( tenant_id = (select auth.uid()) );

create policy obras_update on public.obras
  for update to authenticated
  using      ( id in (select public.current_obra_ids()) )
  with check ( id in (select public.current_obra_ids()) );

-- Sem policy de DELETE: obra não se deleta (arquiva-se). DELETE negado por default.
