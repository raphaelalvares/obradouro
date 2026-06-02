-- 0024_checklist_access.sql  (Fase 3 — grants + helpers de papel + RLS)
-- cria_app (nao-owner) precisa de grant explicito. RLS = 2a camada. As policies de ESCRITA NAO sao
-- so "membro da obra" (isso daria CRUD ao cliente/prestador): elas ja expressam o que da p/ expressar
-- (arquiteto-only; item.update = quem executa), e o guard 0025 cuida da regra fina por-coluna
-- (prestador so 'estado'). Assim, se um guard cair, o cliente AINDA nao escreve e o prestador AINDA
-- nao renomeia/cria/apaga (mais robusto que confiar so no guard).

grant select, insert, update, delete on public.etapas          to cria_app;
grant select, insert, update, delete on public.checklist_itens to cria_app;
-- public.entity_seq_counters: NENHUM grant a cria_app (so o trigger SECURITY DEFINER mexe) — 0023.

-- ===================== Helpers de papel =====================
-- plpgsql (NUNCA language sql: inlining reintroduz recursao de RLS em obra_membros), STABLE,
-- SECURITY DEFINER, search_path travado, owner postgres, revoke public/anon + grant authenticated.
-- Espelham current_obra_ids()/is_arquiteto_ativo() (0011/0019).

-- Papel do usuario corrente na obra (NULL = nao e membro ATIVO). Usado pelo guard 0025 (UPDATE de item).
create or replace function public.meu_papel_obra(p_obra uuid)
returns public.papel_obra
language plpgsql stable security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  select m.papel into v_papel
  from public.obra_membros m
  where m.obra_id = p_obra
    and m.profile_id = (select auth.uid())
    and m.estado = 'ativo';
  return v_papel;
end;
$$;
alter function public.meu_papel_obra(uuid) owner to postgres;
revoke all on function public.meu_papel_obra(uuid) from public, anon;
grant execute on function public.meu_papel_obra(uuid) to authenticated;

-- "Pode executar" (alternar estado de item) = arquiteto OU prestador. Usado na policy itens_update
-- (nega o cliente ja na RLS; a restricao "prestador so estado" continua no guard 0025).
create or replace function public.pode_executar_obra(p_obra uuid)
returns boolean
language plpgsql stable security definer set search_path = '' as $$
begin
  return public.meu_papel_obra(p_obra) in ('arquiteto', 'prestador');
end;
$$;
alter function public.pode_executar_obra(uuid) owner to postgres;
revoke all on function public.pode_executar_obra(uuid) from public, anon;
grant execute on function public.pode_executar_obra(uuid) to authenticated;

-- ===================== RLS (ENABLE sem FORCE) =====================
alter table public.etapas          enable row level security;
alter table public.checklist_itens enable row level security;

-- ETAPAS: SELECT p/ qualquer membro ativo (arquiteto/cliente/prestador veem a arvore).
drop policy if exists etapas_select on public.etapas;
create policy etapas_select on public.etapas
  for select to authenticated
  using ( obra_id in (select public.current_obra_ids()) );

-- INSERT/UPDATE/DELETE de ETAPAS: so arquiteto ativo (na propria RLS; o guard 0025 backstopa).
drop policy if exists etapas_insert on public.etapas;
create policy etapas_insert on public.etapas
  for insert to authenticated
  with check ( public.is_arquiteto_ativo(obra_id) );
drop policy if exists etapas_update on public.etapas;
create policy etapas_update on public.etapas
  for update to authenticated
  using      ( public.is_arquiteto_ativo(obra_id) )
  with check ( public.is_arquiteto_ativo(obra_id) );
drop policy if exists etapas_delete on public.etapas;
create policy etapas_delete on public.etapas
  for delete to authenticated
  using ( public.is_arquiteto_ativo(obra_id) );

-- ITENS: SELECT p/ qualquer membro ativo.
drop policy if exists itens_select on public.checklist_itens;
create policy itens_select on public.checklist_itens
  for select to authenticated
  using ( obra_id in (select public.current_obra_ids()) );
-- INSERT/DELETE de itens: so arquiteto.
drop policy if exists itens_insert on public.checklist_itens;
create policy itens_insert on public.checklist_itens
  for insert to authenticated
  with check ( public.is_arquiteto_ativo(obra_id) );
drop policy if exists itens_delete on public.checklist_itens;
create policy itens_delete on public.checklist_itens
  for delete to authenticated
  using ( public.is_arquiteto_ativo(obra_id) );
-- UPDATE de item: arquiteto OU prestador (cliente negado aqui). A regra "prestador so muda 'estado'"
-- e do guard 0025 (RLS WITH CHECK so ve a linha NOVA, nao distingue QUAL coluna mudou).
drop policy if exists itens_update on public.checklist_itens;
create policy itens_update on public.checklist_itens
  for update to authenticated
  using      ( public.pode_executar_obra(obra_id) )
  with check ( public.pode_executar_obra(obra_id) );
