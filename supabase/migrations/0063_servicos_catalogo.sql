-- 0063_servicos_catalogo.sql  (Livro de referências · Fatia 1 — Catálogo de serviços)
-- BIBLIOTECA do ARQUITETO (nível-TENANT, não por obra/projeto): catálogo reutilizável de serviços com
-- CUSTO DE REFERÊNCIA UNITÁRIO (por unidade). É a peça-átomo do livro: os templates de ambiente
-- (Fatia 2) compõem serviços daqui, e a entrada manual do orçamento pode "puxar do catálogo".
--
-- DIFERENÇA-CHAVE p/ orcamento_itens: aqui o custo é UNITÁRIO (R$/unidade), em numeric(14,4) p/ minimizar
-- erro de arredondamento no ida-e-volta (promover: unit = subtotal/qtd; aplicar: subtotal = unit×qtd).
-- O orçamento guarda SUBTOTAL por linha (numeric(14,2)). A conversão (divisão/multiplicação) é feita no
-- backend (fonte única da matemática), nunca no SQL.
--
-- SEM seq humano (ativo da conta, não entidade numerada de obra) e SEM audit (cria_audit_log é escopo
-- obra/projeto; a biblioteca é nível-conta — igual a tenant_branding 0050). RLS self (tenant = auth.uid()).
-- Aplicar como postgres.

begin;

-- ---------------------------------------------------------------------------------------------------
-- (1) Tabela. id = UUID do cliente (dual-ID). descricao_norm = chave natural de dedupe por tenant
--     (computada pelo backend com o MESMO norm_nome do checklist/orçamento: NFKD+sem acento+casefold).
create table if not exists public.servicos_catalogo (
  id                 uuid          primary key,
  tenant_id          uuid          not null references public.profiles(id) on delete cascade,
  descricao          text          not null,
  descricao_norm     text          not null,
  unidade            text,                                   -- m², un, vb, m… (informativo)
  custo_mo           numeric(14,4) not null default 0,       -- R$ por unidade
  custo_material     numeric(14,4) not null default 0,
  custo_equipamento  numeric(14,4) not null default 0,
  etapa_sugerida     text,                                   -- onde a linha costuma cair no orçamento
  ativo             boolean        not null default true,    -- arquivar sem perder histórico de uso
  created_by         uuid          references public.profiles(id) on delete set null,
  created_at         timestamptz   not null default now(),
  updated_at         timestamptz   not null default now()
);
create unique index if not exists uq_servicos_catalogo_tenant_norm
  on public.servicos_catalogo (tenant_id, descricao_norm);
create index if not exists ix_servicos_catalogo_tenant
  on public.servicos_catalogo (tenant_id, ativo, descricao);
drop trigger if exists trg_servicos_catalogo_updated_at on public.servicos_catalogo;
create trigger trg_servicos_catalogo_updated_at
  before update on public.servicos_catalogo for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------------------------------
-- (2) Guard (SECURITY DEFINER, owner postgres): cinto-e-suspensório da RLS. INSERT só p/ o próprio
--     tenant; identidade imutável no UPDATE. ('_guard' < '_updated_at' → roda antes, mas não há
--     dependência de ordem: o updated_at não toca created_at/id/tenant_id.)
create or replace function public.servicos_catalogo_guard()
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
       or new.created_at is distinct from old.created_at
       or new.created_by is distinct from old.created_by then
      raise exception 'identidade do servico e imutavel' using errcode = '42501';
    end if;
    return new;
  end if;
  return old;  -- DELETE
end;
$$;
alter function public.servicos_catalogo_guard() owner to postgres;
drop trigger if exists trg_servicos_catalogo_guard on public.servicos_catalogo;
create trigger trg_servicos_catalogo_guard
  before insert or update or delete on public.servicos_catalogo
  for each row execute function public.servicos_catalogo_guard();

-- ---------------------------------------------------------------------------------------------------
-- (3) Grants + RLS self (espelha tenant_branding 0050): o arquiteto só vê/edita a PRÓPRIA biblioteca.
grant select, insert, update, delete on public.servicos_catalogo to cria_app;
alter table public.servicos_catalogo enable row level security;

drop policy if exists servicos_catalogo_select on public.servicos_catalogo;
create policy servicos_catalogo_select on public.servicos_catalogo
  for select to authenticated
  using ( tenant_id = (select auth.uid()) );

drop policy if exists servicos_catalogo_insert on public.servicos_catalogo;
create policy servicos_catalogo_insert on public.servicos_catalogo
  for insert to authenticated
  with check ( tenant_id = (select auth.uid()) );

drop policy if exists servicos_catalogo_update on public.servicos_catalogo;
create policy servicos_catalogo_update on public.servicos_catalogo
  for update to authenticated
  using      ( tenant_id = (select auth.uid()) )
  with check ( tenant_id = (select auth.uid()) );

drop policy if exists servicos_catalogo_delete on public.servicos_catalogo;
create policy servicos_catalogo_delete on public.servicos_catalogo
  for delete to authenticated
  using ( tenant_id = (select auth.uid()) );

commit;
