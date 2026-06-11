-- 0077_sec_b1_plano_branding_escopo.sql  (Fase 2 — segurança, item B1)
--
-- PROBLEMA: as funções SECURITY DEFINER plano_do_tenant / plano_limite / plano_flag (0020) e
-- branding_do_tenant (0050) aceitam um p_tenant ARBITRÁRIO e estão concedidas a `authenticated`.
-- Pela borda PostgREST (Path B) qualquer usuário autenticado podia chamá-las com o uuid de outro
-- tenant e enumerar plano/limites/flags e nome/logo do escritório alheio. (Pela API/Path A o
-- p_tenant é sempre derivado no servidor — não é explorável; o vetor é só o PostgREST.)
--
-- CHAMADORES LEGÍTIMOS (verificados em código e no banco) — o guard NÃO pode quebrá-los:
--   * self: get_quota / cobranca / branding usam p_tenant = auth.uid();
--   * membro de obra/projeto do tenant: o PDF do checklist é gerado por cliente/prestador (não-dono)
--     e chama branding_do_tenant(dono) e plano_flag(dono, 'export_pdf'|'logo');
--   * triggers de quota (0021/0033): criar/reativar obra usam o próprio tenant (self); o upload de
--     anexo por PRESTADOR chama plano_limite(tenant_da_obra) — e o prestador é membro ativo dela.
--
-- FIX: guard "self OU membro ativo de obra/projeto do p_tenant". Caller NÃO autorizado é tratado
-- como SEM dados (plano cai no 'free'; branding vem vazio) — fecha o oráculo SEM erro e sem
-- quebrar fluxo algum. plano_limite/plano_flag NÃO precisam mudar: delegam a plano_do_tenant e
-- herdam o guard. Defesa-em-profundidade do C3 (desexpor `public` no PostgREST fecha o Path B).

-- Predicado de autorização (espelha current_obra_ids()/current_projeto_ids(), 0011/0036).
create or replace function public.pode_ler_tenant(p_tenant uuid)
returns boolean
language sql stable security definer set search_path = '' as $$
  select p_tenant = (select auth.uid())
      or exists (select 1 from public.obras o
                  where o.tenant_id = p_tenant
                    and o.id in (select public.current_obra_ids()))
      or exists (select 1 from public.projetos pr
                  where pr.tenant_id = p_tenant
                    and pr.id in (select public.current_projeto_ids()));
$$;
alter function public.pode_ler_tenant(uuid) owner to postgres;
revoke all on function public.pode_ler_tenant(uuid) from public, anon;
grant execute on function public.pode_ler_tenant(uuid) to authenticated;

-- plano_do_tenant v2: não autorizado → p_tenant := null → cai no 'free' (mesmo resultado de um
-- tenant sem assinatura). plano_limite/plano_flag herdam por delegarem a esta.
create or replace function public.plano_do_tenant(p_tenant uuid)
returns table (codigo text, nome text, limites jsonb, flags jsonb)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not public.pode_ler_tenant(p_tenant) then
    p_tenant := null;                      -- B1: não vaza o plano de tenant alheio (vira 'free')
  end if;
  return query
    select p.codigo, p.nome, p.limites, p.flags
    from public.planos p
    where p.codigo = coalesce(
      (select a.plano_codigo from public.tenant_assinaturas a where a.tenant_id = p_tenant),
      'free');
end; $$;
alter function public.plano_do_tenant(uuid) owner to postgres;
revoke all on function public.plano_do_tenant(uuid) from public, anon;
grant execute on function public.plano_do_tenant(uuid) to authenticated;

-- branding_do_tenant v2: não autorizado → conjunto vazio (mesmo resultado de um tenant sem marca).
create or replace function public.branding_do_tenant(p_tenant uuid)
returns table (nome_escritorio text, logo_key text, logo_mime text)
language sql stable security definer set search_path = '' as $$
  select b.nome_escritorio, b.logo_key, b.logo_mime
  from public.tenant_branding b
  where b.tenant_id = p_tenant
    and public.pode_ler_tenant(p_tenant);  -- B1: não vaza nome/logo de escritório alheio
$$;
alter function public.branding_do_tenant(uuid) owner to postgres;
revoke all on function public.branding_do_tenant(uuid) from public, anon;
grant execute on function public.branding_do_tenant(uuid) to authenticated;
