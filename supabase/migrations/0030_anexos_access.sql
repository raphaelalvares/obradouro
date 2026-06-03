-- 0030_anexos_access.sql  (Fase 4 — grants + RLS de anexos)
-- cria_app (nao-owner) precisa de grant explicito. RLS = 2a camada; o guard 0031 cuida da regra
-- fina (prestador so apaga o que subiu; imutabilidade) que a RLS WITH CHECK nao expressa.
-- Quem ESCREVE anexo = quem EXECUTA a obra (arquiteto OU prestador) — documentar a execucao e
-- parte do trabalho do prestador. Cliente = read-only (so SELECT). Sem UPDATE: anexo e imutavel
-- (sem policy de update => RLS nega qualquer update; defesa extra no guard 0031).

grant select, insert, delete on public.anexos to cria_app;
-- (sem grant de UPDATE: anexo nao se edita; troca = apaga + sobe outro)

alter table public.anexos enable row level security;

-- SELECT: qualquer membro ATIVO da obra (arquiteto/cliente/prestador veem a galeria).
drop policy if exists anexos_select on public.anexos;
create policy anexos_select on public.anexos
  for select to authenticated
  using ( obra_id in (select public.current_obra_ids()) );

-- INSERT: quem executa (arquiteto OU prestador). Cliente negado aqui; coerencia/papel reforcados no guard.
drop policy if exists anexos_insert on public.anexos;
create policy anexos_insert on public.anexos
  for insert to authenticated
  with check ( public.pode_executar_obra(obra_id) );

-- DELETE: quem executa (arquiteto OU prestador). A regra "prestador so apaga o PROPRIO anexo"
-- e do guard 0031 (RLS USING nao tem como distinguir o dono de forma robusta junto com o papel).
drop policy if exists anexos_delete on public.anexos;
create policy anexos_delete on public.anexos
  for delete to authenticated
  using ( public.pode_executar_obra(obra_id) );
