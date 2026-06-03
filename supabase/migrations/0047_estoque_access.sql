-- 0047_estoque_access.sql  (Fase 6 — grants + RLS)
-- cria_app (nao-owner) precisa de grant explicito. RLS = 2a camada. Espelha o checklist (0024):
-- SELECT p/ qualquer membro ativo; criar/editar/apagar NOTA so arquiteto; CONFERIR item = quem
-- executa em obra (arquiteto OU prestador, igual ao toggle de checklist) — a regra fina "prestador
-- so mexe na conferencia" fica no guard 0048 (RLS WITH CHECK nao distingue QUAL coluna mudou).

grant select, insert, update, delete on public.notas_fiscais to cria_app;
grant select, insert, update, delete on public.nota_itens     to cria_app;

alter table public.notas_fiscais enable row level security;
alter table public.nota_itens    enable row level security;

-- ===================== NOTAS =====================
drop policy if exists notas_select on public.notas_fiscais;
create policy notas_select on public.notas_fiscais
  for select to authenticated
  using ( obra_id in (select public.current_obra_ids()) );

drop policy if exists notas_insert on public.notas_fiscais;
create policy notas_insert on public.notas_fiscais
  for insert to authenticated
  with check ( public.is_arquiteto_ativo(obra_id) );

drop policy if exists notas_update on public.notas_fiscais;
create policy notas_update on public.notas_fiscais
  for update to authenticated
  using      ( public.is_arquiteto_ativo(obra_id) )
  with check ( public.is_arquiteto_ativo(obra_id) );

drop policy if exists notas_delete on public.notas_fiscais;
create policy notas_delete on public.notas_fiscais
  for delete to authenticated
  using ( public.is_arquiteto_ativo(obra_id) );

-- ===================== ITENS =====================
drop policy if exists nota_itens_select on public.nota_itens;
create policy nota_itens_select on public.nota_itens
  for select to authenticated
  using ( obra_id in (select public.current_obra_ids()) );

drop policy if exists nota_itens_insert on public.nota_itens;
create policy nota_itens_insert on public.nota_itens
  for insert to authenticated
  with check ( public.is_arquiteto_ativo(obra_id) );

drop policy if exists nota_itens_delete on public.nota_itens;
create policy nota_itens_delete on public.nota_itens
  for delete to authenticated
  using ( public.is_arquiteto_ativo(obra_id) );

-- UPDATE de item: arquiteto OU prestador (cliente negado aqui). "prestador so a conferencia" = guard 0048.
drop policy if exists nota_itens_update on public.nota_itens;
create policy nota_itens_update on public.nota_itens
  for update to authenticated
  using      ( public.pode_executar_obra(obra_id) )
  with check ( public.pode_executar_obra(obra_id) );
