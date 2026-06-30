-- 0096_acesso_prazo_entrega.sql  (Portal do Cliente — PRAZO de validade do acesso + marco de ENTREGA)
--
-- O arquiteto define, POR E-MAIL (linha de acessos_cliente), até quando o cliente usa o portal:
--   * 'sem_prazo' (default, = comportamento atual);
--   * 'data'      (uma data fixa);
--   * 'entrega'   ("até a entrega da obra" — marco novo no acompanhamento).
-- No vencimento o acesso é BLOQUEADO: o cliente para de ver aquela obra/projeto (a conta dele
-- continua; o arquiteto pode RENOVAR; mantém histórico). O "expirado" é DERIVADO (expira_em <= now()),
-- não um estado armazenado — assim corta no INSTANTE do prazo, sem job/cron.
--
-- COMO BLOQUEIA (o ponto crítico — cortar de verdade, não só na UI): a validade vira `expira_em`
-- (timestamptz) na MEMBERSHIP (obra_membros/projeto_membros). Os helpers de RLS que escopam TUDO ao
-- cliente passam a ignorar membership vencida:
--   * current_obra_ids() / current_projeto_ids()  → some a obra/projeto vencido de toda leitura RLS
--     (e, por tabela, dos checklists/diário/etc. + dos helpers do backend que leem obras/projetos);
--   * meu_papel_obra() / meu_papel_projeto()       → retornam NULL p/ vencido → fecham os GATES que
--     são RPC SECURITY DEFINER (bypassam RLS): decidir_orcamento_versao (0088), decidir_iniciar_obra
--     (0097), e o ramo cliente do revisoes_guard (0076) também classifica por meu_papel.
-- arquiteto/prestador têm expira_em NULL → nunca expiram. `estado_membro` NÃO muda (expiry é predicado
-- temporal ortogonal — não toca os ~18 policies que checam 'ativo').
--
-- "Entrega da obra" hoje NÃO existe (obras só têm status ativa|arquivada). Criado obras.entregue_em +
-- marcar_entrega_obra() (ação do arquiteto, marco no acompanhamento) → expira os acessos 'entrega'.
--
-- Depende de: 0089 (acessos_cliente/reconciliar), 0011/0024/0036 (helpers RLS), 0002/0003/0034
-- (obras/membros/projetos). Aplicar como postgres, após 0095. DEV antes de PROD. Sem backfill.
-- Lição citext ([[portal-cliente-acesso]]): nada de citext sob search_path='' — e-mail comparado já é
-- text aqui (não toco e-mail nesta migration).

begin;

-- ===================== (1) acessos_cliente: o PRAZO (intenção do arquiteto) =====================
alter table public.acessos_cliente
  add column if not exists validade_tipo text not null default 'sem_prazo',
  add column if not exists validade_ate  date;

-- tipo válido + 'data' exige a data. (autorizar sem prazo → 'sem_prazo'/null → passa.)
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'acessos_cliente_validade_chk') then
    alter table public.acessos_cliente
      add constraint acessos_cliente_validade_chk
      check (validade_tipo in ('sem_prazo', 'data', 'entrega')
             and (validade_tipo <> 'data' or validade_ate is not null));
  end if;
end $$;
-- (validade_tipo/validade_ate NÃO entram na lista de imutáveis do acessos_cliente_guard (0089) →
--  já são mutáveis; o arquiteto renova à vontade. Sem mudar o guard.)

-- ===================== (2) expira_em na MEMBERSHIP (onde o RLS impõe) =====================
alter table public.obra_membros    add column if not exists expira_em timestamptz;
alter table public.projeto_membros add column if not exists expira_em timestamptz;
-- só linhas com prazo (cliente); o grosso (arquiteto/prestador) é null e não pesa.
create index if not exists ix_obra_membros_expira
  on public.obra_membros (expira_em) where expira_em is not null;
create index if not exists ix_projeto_membros_expira
  on public.projeto_membros (expira_em) where expira_em is not null;

-- ===================== (3) obras: marco de ENTREGA =====================
alter table public.obras add column if not exists entregue_em timestamptz;  -- null = não entregue

-- ===================== (4) helpers de RLS ficam EXPIRY-AWARE (4 funções) =====================
-- Mesmos corpos de 0011/0036/0024 + o predicado de prazo. now() é seguro: STABLE (constante na
-- statement). expira_em NULL (arquiteto/prestador) sempre passa.

create or replace function public.current_obra_ids()
returns setof uuid language plpgsql stable security definer set search_path = '' as $$
begin
  return query
    select om.obra_id
    from public.obra_membros om
    where om.profile_id = (select auth.uid())
      and om.estado = 'ativo'
      and (om.expira_em is null or om.expira_em > now());  -- vencido NÃO entra
end;
$$;
alter function public.current_obra_ids() owner to postgres;
revoke all on function public.current_obra_ids() from public, anon;
grant execute on function public.current_obra_ids() to authenticated;

create or replace function public.current_projeto_ids()
returns setof uuid language plpgsql stable security definer set search_path = '' as $$
begin
  return query
    select pm.projeto_id
    from public.projeto_membros pm
    where pm.profile_id = (select auth.uid())
      and pm.estado = 'ativo'
      and (pm.expira_em is null or pm.expira_em > now());
end;
$$;
alter function public.current_projeto_ids() owner to postgres;
revoke all on function public.current_projeto_ids() from public, anon;
grant execute on function public.current_projeto_ids() to authenticated;

-- papel NULL p/ vencido → fecha os GATES definer (RPC) que bypassam RLS.
create or replace function public.meu_papel_obra(p_obra uuid)
returns public.papel_obra language plpgsql stable security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  select m.papel into v_papel
  from public.obra_membros m
  where m.obra_id = p_obra
    and m.profile_id = (select auth.uid())
    and m.estado = 'ativo'
    and (m.expira_em is null or m.expira_em > now());
  return v_papel;
end;
$$;
alter function public.meu_papel_obra(uuid) owner to postgres;
revoke all on function public.meu_papel_obra(uuid) from public, anon;
grant execute on function public.meu_papel_obra(uuid) to authenticated;

create or replace function public.meu_papel_projeto(p_projeto uuid)
returns public.papel_obra language plpgsql stable security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  select pm.papel into v_papel
  from public.projeto_membros pm
  where pm.projeto_id = p_projeto
    and pm.profile_id = (select auth.uid())
    and pm.estado = 'ativo'
    and (pm.expira_em is null or pm.expira_em > now());
  return v_papel;
end;
$$;
alter function public.meu_papel_projeto(uuid) owner to postgres;
revoke all on function public.meu_papel_projeto(uuid) from public, anon;
grant execute on function public.meu_papel_projeto(uuid) to authenticated;

-- ===================== (5) propaga a validade do acesso → expira_em da membership =====================
-- Idempotente. Lê a regra do acesso e RECOMPUTA expira_em nas memberships materializadas do cliente
-- (projeto + obra ligada, ou obra direta). Chamada na reconciliação, ao definir/renovar o prazo, e ao
-- marcar/desmarcar a entrega. Só mexe em expira_em → o guard de membros (0073) não barra (papel/
-- profile/obra/estado intactos), e roda tanto no contexto do arquiteto quanto do cliente.
create or replace function public.aplicar_validade_acesso(p_acesso uuid)
returns void language plpgsql security definer set search_path = '' as $$
declare
  v_profile   uuid;
  v_projeto   uuid;
  v_obra      uuid;
  v_tipo      text;
  v_ate       date;
  v_obra_proj uuid;        -- obra ligada ao projeto (quando o acesso é de projeto)
  v_entregue  timestamptz;
  v_exp       timestamptz;
begin
  select ac.profile_id, ac.projeto_id, ac.obra_id, ac.validade_tipo, ac.validade_ate
    into v_profile, v_projeto, v_obra, v_tipo, v_ate
  from public.acessos_cliente ac where ac.id = p_acesso;
  if not found or v_profile is null then
    return;  -- acesso inexistente ou ainda não reivindicado: nada a materializar
  end if;

  -- obra-alvo da "entrega": a própria (acesso de obra) ou a obra ligada ao projeto
  if v_obra is not null then
    select o.entregue_em into v_entregue from public.obras o where o.id = v_obra;
  elsif v_projeto is not null then
    select pj.obra_id into v_obra_proj from public.projetos pj where pj.id = v_projeto;
    if v_obra_proj is not null then
      select o.entregue_em into v_entregue from public.obras o where o.id = v_obra_proj;
    end if;
  end if;

  -- expira_em pela regra do tipo. 'data' vale o dia INTEIRO no fuso do tenant (Brasil) — sem o
  -- `at time zone` o (data+1)::timestamptz cairia em 00:00 UTC = 21:00 BRT do dia anterior (corta 3h
  -- cedo / "nasce vencido"). Mesmo padrão de lembretes.py. Literal de fuso é pg_catalog-safe.
  if v_tipo = 'data' then
    v_exp := (v_ate + 1)::timestamp at time zone 'America/Sao_Paulo';
  elsif v_tipo = 'entrega' then
    v_exp := v_entregue;                  -- null enquanto a obra não foi entregue
  else
    v_exp := null;                        -- sem_prazo
  end if;

  if v_projeto is not null then
    update public.projeto_membros set expira_em = v_exp
      where projeto_id = v_projeto and profile_id = v_profile and papel = 'cliente';
    if v_obra_proj is not null then
      update public.obra_membros set expira_em = v_exp
        where obra_id = v_obra_proj and profile_id = v_profile and papel = 'cliente';
    end if;
  end if;
  if v_obra is not null then
    update public.obra_membros set expira_em = v_exp
      where obra_id = v_obra and profile_id = v_profile and papel = 'cliente';
  end if;
end;
$$;
alter function public.aplicar_validade_acesso(uuid) owner to postgres;
revoke all on function public.aplicar_validade_acesso(uuid) from public, anon;
grant execute on function public.aplicar_validade_acesso(uuid) to authenticated;

-- ===================== (6) reconciliar (0089) agora carimba expira_em + filtra contexto =====================
-- Igual à 0089 + (a) perform aplicar_validade_acesso após materializar (carimba expira_em pela
-- validade do acesso); (b) o contexto (projetos/obras do cliente) exclui vínculo VENCIDO.
create or replace function public.reconciliar_acessos_cliente()
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  v_uid        uuid := (select auth.uid());
  v_email      text;   -- text (não citext): sob search_path='' citext não resolve. ::text é binário.
  v_confirmado boolean := false;
  v_proj       jsonb := '[]'::jsonb;
  v_obras      jsonb := '[]'::jsonb;
  v_arq        boolean;
  v_cli_any    boolean;
  r            record;
begin
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;
  select u.email::text, (u.email_confirmed_at is not null)
    into v_email, v_confirmado
  from auth.users u where u.id = v_uid;

  if v_email is not null and v_confirmado then
    for r in
      select ac.id, ac.tenant_id, ac.projeto_id, ac.obra_id
      from public.acessos_cliente ac
      where lower(ac.email::text) = lower(v_email) and ac.profile_id is null
      for update
    loop
      update public.acessos_cliente set profile_id = v_uid, estado = 'ativo' where id = r.id;

      if r.projeto_id is not null then
        insert into public.projeto_membros (projeto_id, profile_id, papel, estado, invited_by)
        values (r.projeto_id, v_uid, 'cliente', 'ativo', r.tenant_id)
        on conflict (projeto_id, profile_id) do nothing;
        insert into public.obra_membros (obra_id, profile_id, papel, estado, invited_by)
        select pj.obra_id, v_uid, 'cliente', 'ativo', r.tenant_id
        from public.projetos pj
        where pj.id = r.projeto_id and pj.obra_id is not null
        on conflict (obra_id, profile_id) do nothing;
      end if;

      if r.obra_id is not null then
        insert into public.obra_membros (obra_id, profile_id, papel, estado, invited_by)
        values (r.obra_id, v_uid, 'cliente', 'ativo', r.tenant_id)
        on conflict (obra_id, profile_id) do nothing;
      end if;

      -- carimba expira_em conforme a validade do acesso (sem_prazo/data/entrega)
      perform public.aplicar_validade_acesso(r.id);
    end loop;
  end if;

  -- contexto: projetos/obras onde sou CLIENTE ativo E NÃO vencido (vencido some do portal)
  select coalesce(jsonb_agg(jsonb_build_object(
           'id', pj.id, 'nome', pj.nome, 'seq_humano', pj.seq_humano, 'obra_id', pj.obra_id)
           order by pj.created_at), '[]'::jsonb)
    into v_proj
  from public.projeto_membros pm
  join public.projetos pj on pj.id = pm.projeto_id
  where pm.profile_id = v_uid and pm.papel = 'cliente' and pm.estado = 'ativo'
    and (pm.expira_em is null or pm.expira_em > now());

  select coalesce(jsonb_agg(jsonb_build_object(
           'id', o.id, 'nome', o.nome, 'seq_humano', o.seq_humano, 'status', o.status)
           order by o.created_at), '[]'::jsonb)
    into v_obras
  from public.obra_membros om
  join public.obras o on o.id = om.obra_id
  where om.profile_id = v_uid and om.papel = 'cliente' and om.estado = 'ativo'
    and (om.expira_em is null or om.expira_em > now());

  v_arq := exists (select 1 from public.obras    where tenant_id = v_uid)
        or exists (select 1 from public.projetos where tenant_id = v_uid);

  -- "é cliente em algum lugar" IGNORANDO o prazo (vínculo existe, mesmo vencido) — distingue um
  -- cliente expirado de um arquiteto novo (ambos têm eh_cliente=false). O front roteia o portal por
  -- (not eh_arquiteto and tem_papel_cliente) → o cliente vencido cai no portal (estado expirado),
  -- não no painel do arquiteto.
  v_cli_any := exists (
                 select 1 from public.projeto_membros where profile_id = v_uid and papel = 'cliente')
            or exists (
                 select 1 from public.obra_membros    where profile_id = v_uid and papel = 'cliente');

  return jsonb_build_object(
    'eh_arquiteto',      v_arq,
    'eh_cliente',        (jsonb_array_length(v_proj) > 0 or jsonb_array_length(v_obras) > 0),
    'tem_papel_cliente', v_cli_any,
    'projetos',          v_proj,
    'obras',             v_obras);
end;
$$;
alter function public.reconciliar_acessos_cliente() owner to postgres;
revoke all on function public.reconciliar_acessos_cliente() from public, anon;
grant execute on function public.reconciliar_acessos_cliente() to authenticated;

-- ===================== (7) marco de ENTREGA da obra (arquiteto) =====================
-- Seta/limpa obras.entregue_em e reaplica a validade dos acessos 'entrega' que miram esta obra
-- (direta ou via projeto). Marcar entregue → expira esses acessos; desmarcar → restaura (renova).
create or replace function public.marcar_entrega_obra(p_obra uuid, p_entregue boolean)
returns timestamptz language plpgsql security definer set search_path = '' as $$
declare
  v_ts timestamptz;
  a    record;
begin
  if not public.is_arquiteto_ativo(p_obra) then
    raise exception 'apenas o arquiteto pode marcar a entrega' using errcode = '42501';
  end if;
  v_ts := case when p_entregue then now() else null end;
  update public.obras set entregue_em = v_ts where id = p_obra;

  for a in
    select ac.id
    from public.acessos_cliente ac
    where ac.validade_tipo = 'entrega' and ac.profile_id is not null
      and ( ac.obra_id = p_obra
            or ac.projeto_id in (select pj.id from public.projetos pj where pj.obra_id = p_obra) )
  loop
    perform public.aplicar_validade_acesso(a.id);
  end loop;

  return v_ts;
end;
$$;
alter function public.marcar_entrega_obra(uuid, boolean) owner to postgres;
revoke all on function public.marcar_entrega_obra(uuid, boolean) from public, anon;
grant execute on function public.marcar_entrega_obra(uuid, boolean) to authenticated;

-- ===================== (8) virar obra HERDA o expira_em do projeto (corrige vazamento) =====================
-- Recria vincular_cliente_na_obra (0089) p/ COPIAR o expira_em do projeto_membros do cliente. Sem isso,
-- quando o cliente é autorizado num projeto SEM obra, se cadastra (expira_em carimbado só no
-- projeto_membros), e a obra nasce depois (virar_obra/converter → esta função), a obra_membros entrava
-- com expira_em NULL = acesso à OBRA nunca vencia, mesmo com o projeto já vencido. Herdar o prazo
-- fecha o furo; 'entrega' fica NULL (obra nova não-entregue) e a entrega posterior reaplica.
create or replace function public.vincular_cliente_na_obra(p_projeto uuid)
returns void language plpgsql security definer set search_path = '' as $$
declare
  v_obra uuid;
begin
  select obra_id into v_obra from public.projetos where id = p_projeto;
  if v_obra is null then
    return;
  end if;
  insert into public.obra_membros (obra_id, profile_id, papel, estado, invited_by, expira_em)
  select v_obra, pm.profile_id, 'cliente', 'ativo', pm.invited_by, pm.expira_em
  from public.projeto_membros pm
  where pm.projeto_id = p_projeto and pm.papel = 'cliente' and pm.estado = 'ativo'
  on conflict (obra_id, profile_id) do nothing;
end;
$$;
alter function public.vincular_cliente_na_obra(uuid) owner to postgres;
revoke all on function public.vincular_cliente_na_obra(uuid) from public, anon;
grant execute on function public.vincular_cliente_na_obra(uuid) to authenticated;

commit;
