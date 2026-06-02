-- 0015_rls_pendentes.sql  (Fase 1)
-- Rótulo MAGRO para quem está PENDENTE: vê só {nome da obra, seq, quem convidou}.
-- Escopo no próprio WHERE (não confia na RLS da base); SECURITY DEFINER owner postgres.

create or replace function public.minhas_obras_pendentes()
returns table (obra_id uuid, obra_nome text, seq_humano bigint, invited_by_nome text)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  return query
    select o.id, o.nome, o.seq_humano, p.nome
    from public.obra_membros om
    join public.obras o on o.id = om.obra_id
    left join public.profiles p on p.id = om.invited_by
    where om.profile_id = (select auth.uid())     -- escopo no WHERE
      and om.estado = 'pendente';
end;
$$;

alter function public.minhas_obras_pendentes() owner to postgres;
revoke all on function public.minhas_obras_pendentes() from public, anon;
grant execute on function public.minhas_obras_pendentes() to authenticated;
