-- 0067_efetivo_funcoes.sql  (Fatia C — efetivo do diário por FUNÇÃO/cargo)
-- O campo "efetivo (pessoas)" do diário (0066) era um número solto e confuso ("12 o quê?"). Troca por
-- um RDO de verdade: EFETIVO POR FUNÇÃO (2 pedreiros, 3 serventes…), poka-yoke. Para isso:
--   (1) FUNCOES — biblioteca REUTILIZÁVEL no tenant (escritório), igual a Equipes (0065): cargos/
--       funções (Pedreiro, Servente, Mestre…). RLS self (tenant = auth.uid()), SEM seq/audit.
--   (2) diario_obra.efetivo_itens jsonb — a quebra do dia [{funcao_id, nome(snapshot), qtd}]. O total
--       continua em diario_obra.efetivo (mantido pelo backend = soma das qtds). Sem tabela-filha: a
--       quebra é um value-object do diário, editado junto com a entrada.
--   (3) funcoes_da_obra() SECURITY DEFINER — o PRESTADOR que preenche o diário precisa LER a biblioteca
--       do DONO da obra (a RLS self da funcoes bloquearia a leitura cross-tenant). Esta função, dona
--       postgres, devolve as funções do tenant da obra a QUALQUER membro da obra (escolhe no picker).
--   (4) recria o diario_obra_guard (0066) acrescentando a coerência cross-tenant do efetivo_itens.
-- Aplicar como postgres, na ordem (depende de 0065 equipes-pattern e 0066 diario). DEV antes de PROD.

begin;

-- ===================================================================================================
-- (1) FUNCOES — biblioteca por TENANT (espelha equipes 0065, sem cor/contato). id = UUID do cliente.
--     nome_norm = chave de dedupe por tenant (mesmo norm do checklist/catálogo).
create table if not exists public.funcoes (
  id          uuid        primary key,
  tenant_id   uuid        not null references public.profiles(id) on delete cascade,
  nome        text        not null,
  nome_norm   text        not null,
  ativo       boolean     not null default true,       -- arquivar sem perder o histórico de uso
  created_by  uuid        references public.profiles(id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create unique index if not exists uq_funcoes_tenant_norm on public.funcoes (tenant_id, nome_norm);
create index if not exists ix_funcoes_tenant on public.funcoes (tenant_id, ativo, nome);
drop trigger if exists trg_funcoes_updated_at on public.funcoes;
create trigger trg_funcoes_updated_at
  before update on public.funcoes for each row execute function public.set_updated_at();

-- Guard (SECURITY DEFINER, owner postgres): cinto-e-suspensório da RLS. INSERT só p/ o próprio tenant;
-- identidade imutável no UPDATE. NÃO checa created_by (on delete set null dispararia o guard) — 0065.
create or replace function public.funcoes_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if new.tenant_id is distinct from (select auth.uid()) then
      raise exception 'tenant_id incoerente' using errcode = '42501';
    end if;
    return new;
  end if;
  if tg_op = 'UPDATE' then
    if new.id is distinct from old.id
       or new.tenant_id is distinct from old.tenant_id
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade da funcao e imutavel' using errcode = '42501';
    end if;
    return new;
  end if;
  return old;  -- DELETE
end;
$$;
alter function public.funcoes_guard() owner to postgres;
drop trigger if exists trg_funcoes_guard on public.funcoes;
create trigger trg_funcoes_guard
  before insert or update or delete on public.funcoes
  for each row execute function public.funcoes_guard();

-- Grants + RLS self (espelha equipes 0065 / servicos_catalogo 0063).
grant select, insert, update, delete on public.funcoes to cria_app;
alter table public.funcoes enable row level security;

drop policy if exists funcoes_select on public.funcoes;
create policy funcoes_select on public.funcoes
  for select to authenticated using ( tenant_id = (select auth.uid()) );
drop policy if exists funcoes_insert on public.funcoes;
create policy funcoes_insert on public.funcoes
  for insert to authenticated with check ( tenant_id = (select auth.uid()) );
drop policy if exists funcoes_update on public.funcoes;
create policy funcoes_update on public.funcoes
  for update to authenticated
  using      ( tenant_id = (select auth.uid()) )
  with check ( tenant_id = (select auth.uid()) );
drop policy if exists funcoes_delete on public.funcoes;
create policy funcoes_delete on public.funcoes
  for delete to authenticated using ( tenant_id = (select auth.uid()) );

-- ===================================================================================================
-- (2) diario_obra.efetivo_itens — a quebra do dia por função. CHECK garante que é sempre um array (a
--     coluna `efetivo` segue como o TOTAL, mantido pelo backend = soma das qtds). Sem FK p/ funcoes:
--     o `nome` gravado é um SNAPSHOT (apagar/renomear a função NÃO mexe no histórico do diário).
alter table public.diario_obra
  add column if not exists efetivo_itens jsonb not null default '[]'::jsonb;
alter table public.diario_obra drop constraint if exists diario_efetivo_itens_arr;
alter table public.diario_obra
  add constraint diario_efetivo_itens_arr check (jsonb_typeof(efetivo_itens) = 'array');

-- coerência cross-tenant do efetivo: TODO funcao_id citado tem de ser do MESMO tenant do diário.
-- Roda dentro do guard (owner postgres) → enxerga funcoes de qualquer tenant (a RLS self não a barra).
create or replace function public.diario_efetivo_coerente(p_itens jsonb, p_tenant uuid)
returns boolean
language sql security definer set search_path = '' stable as $$
  select not exists (
    select 1
    from jsonb_array_elements(coalesce(p_itens, '[]'::jsonb)) e
    where not exists (
      select 1 from public.funcoes f
      where f.id = (e->>'funcao_id')::uuid and f.tenant_id = p_tenant
    )
  );
$$;
alter function public.diario_efetivo_coerente(jsonb, uuid) owner to postgres;

-- ===================================================================================================
-- (3) RECRIA o diario_obra_guard (0066) + coerência do efetivo_itens. TUDO o mais é idêntico ao 0066
--     (coerência tenant/obra, identidade imutável, arquiteto qualquer / prestador só a própria).
create or replace function public.diario_obra_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    if not public.diario_efetivo_coerente(new.efetivo_itens, new.tenant_id) then
      raise exception 'funcao de outro tenant no efetivo' using errcode = '42501';
    end if;
    if not public.pode_executar_obra(new.obra_id) then
      raise exception 'apenas quem executa a obra registra no diario' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    if new.id is distinct from old.id
       or new.obra_id is distinct from old.obra_id
       or new.tenant_id is distinct from old.tenant_id
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade do diario e imutavel' using errcode = '42501';
    end if;
    if new.efetivo_itens is distinct from old.efetivo_itens
       and not public.diario_efetivo_coerente(new.efetivo_itens, new.tenant_id) then
      raise exception 'funcao de outro tenant no efetivo' using errcode = '42501';
    end if;
    v_papel := public.meu_papel_obra(old.obra_id);
    if v_papel = 'arquiteto' then
      return new;
    elsif v_papel = 'prestador' and old.created_by is not distinct from (select auth.uid()) then
      return new;  -- prestador edita só a PRÓPRIA entrada
    else
      raise exception 'sem permissao para editar este registro' using errcode = '42501';
    end if;
  end if;

  -- DELETE
  v_papel := public.meu_papel_obra(old.obra_id);
  if v_papel = 'arquiteto' then
    return old;
  elsif v_papel = 'prestador' and old.created_by is not distinct from (select auth.uid()) then
    return old;
  else
    raise exception 'sem permissao para apagar este registro' using errcode = '42501';
  end if;
end;
$$;
alter function public.diario_obra_guard() owner to postgres;
-- trigger trg_diario_obra_guard (0066) já aponta p/ esta função; não recriar.

-- ===================================================================================================
-- (4) funcoes_da_obra() — picker do diário. Devolve as funções do tenant DONO da obra a QUALQUER
--     membro da obra (inclui o prestador, que tem auth.uid() != tenant → a RLS self bloquearia ler).
--     p_so_ativos=true (padrão) p/ o picker; false p/ a VALIDAÇÃO no backend (edição de entrada antiga
--     que cita função já arquivada não pode quebrar). owner postgres (bypassa a RLS self).
create or replace function public.funcoes_da_obra(p_obra uuid, p_so_ativos boolean default true)
returns table (id uuid, nome text)
language sql security definer set search_path = '' stable as $$
  select f.id, f.nome
  from public.funcoes f
  join public.obras o on o.tenant_id = f.tenant_id
  where o.id = p_obra
    and o.id in (select public.current_obra_ids())   -- só membro da obra enxerga
    and (not p_so_ativos or f.ativo)
  order by f.nome;
$$;
alter function public.funcoes_da_obra(uuid, boolean) owner to postgres;
grant execute on function public.funcoes_da_obra(uuid, boolean) to cria_app;

commit;
