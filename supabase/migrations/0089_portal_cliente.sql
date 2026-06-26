-- 0089_portal_cliente.sql  (Portal do Cliente — autocadastro por e-mail, escopo projeto+obra)
--
-- O arquiteto PRÉ-AUTORIZA um e-mail no projeto (onde nasce o orçamento). O cliente se AUTOCADASTRA
-- (e-mail + senha à escolha dele) pelo Supabase Auth comum e, no 1º login, a função definer
-- reconciliar_acessos_cliente() casa o e-mail CONFIRMADO do caller com a pré-autorização e materializa
-- os vínculos (projeto_membros 'cliente'/'ativo' e, se já há obra, obra_membros). Sem SERVICE_ROLE,
-- sem magic-link nosso.
--
-- POR QUE definer: projeto_membros/obra_membros exigem profile_id (FK) — que só existe DEPOIS do
-- cadastro — e as policies de INSERT exigem ARQUITETO ativo (não há self-insert). A pré-autorização
-- por e-mail mora numa tabela à parte; o vínculo só pode ser criado por uma RPC SECURITY DEFINER que
-- valida `email do caller == email pré-autorizado` (fronteira = e-mail confirmado pelo Supabase).
-- Espelha o padrão criar_obra/resgatar_codigo (0018/0041).
--
-- Depende de: 0001 (citext/profiles/papel_obra), 0002/0003 (obras/obra_membros), 0034 (projetos/
-- projeto_membros). Aplicar como postgres, após 0088. DEV antes de PROD.

begin;

-- ===================== (1) tabela acessos_cliente (pré-autorização por e-mail, nível-tenant) =====
create table if not exists public.acessos_cliente (
  id          uuid        primary key default gen_random_uuid(),
  tenant_id   uuid        not null references public.profiles(id) on delete cascade,  -- o arquiteto
  projeto_id  uuid        references public.projetos(id) on delete cascade,
  obra_id     uuid        references public.obras(id)    on delete cascade,
  email       citext      not null,
  profile_id  uuid        references public.profiles(id) on delete set null,  -- preenchido ao reconciliar
  estado      text        not null default 'pendente',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint acessos_cliente_alvo_chk   check (projeto_id is not null or obra_id is not null),
  constraint acessos_cliente_estado_chk check (estado in ('pendente', 'ativo'))
);
-- não duplica a autorização do mesmo e-mail no mesmo alvo (parciais: só onde a coluna existe)
create unique index if not exists uq_acessos_cliente_projeto_email
  on public.acessos_cliente (projeto_id, email) where projeto_id is not null;
create unique index if not exists uq_acessos_cliente_obra_email
  on public.acessos_cliente (obra_id, email) where obra_id is not null;
create index if not exists ix_acessos_cliente_tenant on public.acessos_cliente (tenant_id);
-- sustenta a reconciliação (busca por e-mail ainda não reivindicado)
create index if not exists ix_acessos_cliente_email_pendente
  on public.acessos_cliente (email) where profile_id is null;

drop trigger if exists trg_acessos_cliente_updated_at on public.acessos_cliente;
create trigger trg_acessos_cliente_updated_at
  before update on public.acessos_cliente for each row execute function public.set_updated_at();

-- ===================== (2) guard (SECURITY DEFINER) — identidade imutável, anti cross-tenant =====
create or replace function public.acessos_cliente_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if new.tenant_id is distinct from (select auth.uid()) then
      raise exception 'tenant_id incoerente' using errcode = '42501';
    end if;
    if new.projeto_id is not null and not exists (
         select 1 from public.projetos p where p.id = new.projeto_id and p.tenant_id = new.tenant_id) then
      raise exception 'projeto de outro tenant' using errcode = '42501';
    end if;
    if new.obra_id is not null and not exists (
         select 1 from public.obras o where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'obra de outro tenant' using errcode = '42501';
    end if;
    return new;
  end if;
  if tg_op = 'UPDATE' then
    -- só estado/profile_id mudam (e só pela reconciliação definer); o resto é imutável.
    -- email comparado como text: sob search_path='' o operador de citext (schema da extensão) não
    -- resolve; o cast ::text é binário e lower()/= de text são pg_catalog.
    if new.id is distinct from old.id
       or new.tenant_id is distinct from old.tenant_id
       or new.projeto_id is distinct from old.projeto_id
       or new.obra_id is distinct from old.obra_id
       or new.email::text is distinct from old.email::text
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade do acesso e imutavel' using errcode = '42501';
    end if;
    return new;
  end if;
  return old;  -- DELETE
end;
$$;
alter function public.acessos_cliente_guard() owner to postgres;
drop trigger if exists trg_acessos_cliente_guard on public.acessos_cliente;
create trigger trg_acessos_cliente_guard
  before insert or update or delete on public.acessos_cliente
  for each row execute function public.acessos_cliente_guard();

-- ===================== (3) grants + RLS self do arquiteto (espelha servicos_catalogo 0063) =====
-- O cliente NÃO lê/escreve esta tabela direto (só o arquiteto dono); o vínculo é via a RPC definer.
grant select, insert, update, delete on public.acessos_cliente to cria_app;
alter table public.acessos_cliente enable row level security;

drop policy if exists acessos_cliente_select on public.acessos_cliente;
create policy acessos_cliente_select on public.acessos_cliente
  for select to authenticated using ( tenant_id = (select auth.uid()) );

drop policy if exists acessos_cliente_insert on public.acessos_cliente;
create policy acessos_cliente_insert on public.acessos_cliente
  for insert to authenticated with check ( tenant_id = (select auth.uid()) );

drop policy if exists acessos_cliente_update on public.acessos_cliente;
create policy acessos_cliente_update on public.acessos_cliente
  for update to authenticated
  using      ( tenant_id = (select auth.uid()) )
  with check ( tenant_id = (select auth.uid()) );

drop policy if exists acessos_cliente_delete on public.acessos_cliente;
create policy acessos_cliente_delete on public.acessos_cliente
  for delete to authenticated using ( tenant_id = (select auth.uid()) );

-- ===================== (4) reconciliar: casa e-mail confirmado × pré-autorização e vincula =====
-- Idempotente. Fronteira de segurança = `ac.email = email do profiles do auth.uid()`: com "Confirm
-- email" ON no Supabase, ter sessão ⇒ e-mail comprovado ⇒ ninguém reivindica acesso alheio. Devolve o
-- contexto de roteamento (eh_arquiteto/eh_cliente) + as listas de projetos/obras do cliente.
create or replace function public.reconciliar_acessos_cliente()
returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_uid        uuid := (select auth.uid());
  -- text (não citext): sob search_path='' o tipo/operador de citext (schema da extensão) não resolve.
  -- O cast ::text é binário e lower()/= de text são pg_catalog → match case-insensitive seguro.
  v_email      text;
  v_confirmado boolean := false;
  v_proj       jsonb := '[]'::jsonb;
  v_obras      jsonb := '[]'::jsonb;
  v_arq        boolean;
  r            record;
begin
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;
  -- E-mail + confirmação direto do auth.users (fonte autoritativa; profiles é mirror e pode defasar
  -- se o e-mail mudar). Só VINCULA com e-mail CONFIRMADO — defesa-em-profundidade: o "Confirm email"
  -- do Supabase é a fronteira primária, mas a checagem aqui torna a intenção explícita no código.
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
        -- projeto já tem obra? o cliente entra também na obra (1 acesso cobre projeto+obra)
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
    end loop;
  end if;

  -- contexto: projetos/obras onde sou CLIENTE ativo (após vincular)
  select coalesce(jsonb_agg(jsonb_build_object(
           'id', pj.id, 'nome', pj.nome, 'seq_humano', pj.seq_humano, 'obra_id', pj.obra_id)
           order by pj.created_at), '[]'::jsonb)
    into v_proj
  from public.projeto_membros pm
  join public.projetos pj on pj.id = pm.projeto_id
  where pm.profile_id = v_uid and pm.papel = 'cliente' and pm.estado = 'ativo';

  select coalesce(jsonb_agg(jsonb_build_object(
           'id', o.id, 'nome', o.nome, 'seq_humano', o.seq_humano, 'status', o.status)
           order by o.created_at), '[]'::jsonb)
    into v_obras
  from public.obra_membros om
  join public.obras o on o.id = om.obra_id
  where om.profile_id = v_uid and om.papel = 'cliente' and om.estado = 'ativo';

  -- arquiteto = dono de algum projeto/obra (definer enxerga tudo → checagem confiável)
  v_arq := exists (select 1 from public.obras    where tenant_id = v_uid)
        or exists (select 1 from public.projetos where tenant_id = v_uid);

  return jsonb_build_object(
    'eh_arquiteto', v_arq,
    'eh_cliente',   (jsonb_array_length(v_proj) > 0 or jsonb_array_length(v_obras) > 0),
    'projetos',     v_proj,
    'obras',        v_obras);
end;
$$;
alter function public.reconciliar_acessos_cliente() owner to postgres;
revoke all on function public.reconciliar_acessos_cliente() from public, anon;
grant execute on function public.reconciliar_acessos_cliente() to authenticated;

-- ===================== (5) propagar cliente do projeto p/ a obra (ao virar obra) =====
-- Chamada pelo backend em virar_obra/converter quando a obra é criada DEPOIS do cliente já cadastrado.
-- Definer: insere obra_membros independe da RLS (DRY com a reconciliação). Idempotente.
create or replace function public.vincular_cliente_na_obra(p_projeto uuid)
returns void
language plpgsql security definer set search_path = '' as $$
declare
  v_obra uuid;
begin
  select obra_id into v_obra from public.projetos where id = p_projeto;
  if v_obra is null then
    return;
  end if;
  insert into public.obra_membros (obra_id, profile_id, papel, estado, invited_by)
  select v_obra, pm.profile_id, 'cliente', 'ativo', pm.invited_by
  from public.projeto_membros pm
  where pm.projeto_id = p_projeto and pm.papel = 'cliente' and pm.estado = 'ativo'
  on conflict (obra_id, profile_id) do nothing;
end;
$$;
alter function public.vincular_cliente_na_obra(uuid) owner to postgres;
revoke all on function public.vincular_cliente_na_obra(uuid) from public, anon;
grant execute on function public.vincular_cliente_na_obra(uuid) to authenticated;

commit;
