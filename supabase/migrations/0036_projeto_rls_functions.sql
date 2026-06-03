-- 0036_projeto_rls_functions.sql  (Fase 5 — helpers de RLS de projeto + extensão de profiles_select)
-- Espelham current_obra_ids()/is_arquiteto_ativo()/meu_papel_obra() (0011/0019/0024). plpgsql
-- (NUNCA language sql: inlining reintroduz recursão de RLS via projeto_membros), STABLE, SECURITY
-- DEFINER (isenção de owner quebra a recursão), search_path travado, owner postgres.

-- Projetos onde o usuário é membro ATIVO (pendente NUNCA entra → não vê dados do projeto).
create or replace function public.current_projeto_ids()
returns setof uuid
language plpgsql stable security definer set search_path = '' as $$
begin
  return query
    select pm.projeto_id
    from public.projeto_membros pm
    where pm.profile_id = (select auth.uid())
      and pm.estado = 'ativo';
end;
$$;
alter function public.current_projeto_ids() owner to postgres;
revoke all on function public.current_projeto_ids() from public, anon;
grant execute on function public.current_projeto_ids() to authenticated;

-- Papel do usuário corrente no projeto (NULL = não é membro ATIVO).
create or replace function public.meu_papel_projeto(p_projeto uuid)
returns public.papel_obra
language plpgsql stable security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  select pm.papel into v_papel
  from public.projeto_membros pm
  where pm.projeto_id = p_projeto
    and pm.profile_id = (select auth.uid())
    and pm.estado = 'ativo';
  return v_papel;
end;
$$;
alter function public.meu_papel_projeto(uuid) owner to postgres;
revoke all on function public.meu_papel_projeto(uuid) from public, anon;
grant execute on function public.meu_papel_projeto(uuid) to authenticated;

-- Arquiteto ativo do projeto (usado por policies/guards/RPCs).
create or replace function public.is_arquiteto_ativo_projeto(p_projeto uuid)
returns boolean
language plpgsql stable security definer set search_path = '' as $$
begin
  return exists (
    select 1 from public.projeto_membros pm
    where pm.projeto_id = p_projeto
      and pm.profile_id = (select auth.uid())
      and pm.papel = 'arquiteto'
      and pm.estado = 'ativo'
  );
end;
$$;
alter function public.is_arquiteto_ativo_projeto(uuid) owner to postgres;
revoke all on function public.is_arquiteto_ativo_projeto(uuid) from public, anon;
grant execute on function public.is_arquiteto_ativo_projeto(uuid) to authenticated;

-- Estende profiles_select (0012): membros ATIVOS de um projeto veem o nome um do outro (igual ao
-- ramo de obra). Usa current_projeto_ids() (definer, quebra recursão) — NUNCA subselect direto em
-- projeto_membros dentro da policy (recriaria recursão via a RLS de projeto_membros).
drop policy if exists profiles_select on public.profiles;
create policy profiles_select on public.profiles
  for select to authenticated
  using (
        id = (select auth.uid())
     or id in (
          select om.profile_id
          from public.obra_membros om
          where om.obra_id in (select public.current_obra_ids())
        )
     or id in (
          select pm.profile_id
          from public.projeto_membros pm
          where pm.projeto_id in (select public.current_projeto_ids())
        )
  );
