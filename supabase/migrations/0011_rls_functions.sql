-- 0011_rls_functions.sql  (Fase 1)
-- Função central que QUEBRA a recursão de RLS: retorna as obras onde o usuário atual
-- é membro ATIVO. plpgsql (NUNCA language sql — seria inlined e a recursão voltaria),
-- STABLE, search_path travado, owner postgres (ignora RLS por isenção de owner).

create or replace function public.current_obra_ids()
returns setof uuid
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  return query
    select om.obra_id
    from public.obra_membros om
    where om.profile_id = (select auth.uid())
      and om.estado = 'ativo';        -- pendente NUNCA entra na lista de obras visíveis
end;
$$;

alter function public.current_obra_ids() owner to postgres;
revoke all on function public.current_obra_ids() from public, anon;
grant execute on function public.current_obra_ids() to authenticated;

-- auth.uid() (definição oficial Supabase) lê current_setting('request.jwt.claims')::jsonb->>'sub'.
-- O backend faz set_config('request.jwt.claims', ..., true) por transação → auth.uid() funciona.
