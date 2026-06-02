-- 0016_rls_obra_codigos.sql  (Fase 1)
-- Só membro ATIVO da obra (na prática, o arquiteto — validado na API) gerencia códigos.
-- O CONSUMO do código (alguém de fora entrando) NÃO passa por aqui — é via
-- resgatar_codigo_obra (0018, SECURITY DEFINER), pois quem entra ainda não é membro.

create policy obra_codigos_all on public.obra_codigos
  for all to authenticated
  using      ( obra_id in (select public.current_obra_ids()) )
  with check ( obra_id in (select public.current_obra_ids()) );
