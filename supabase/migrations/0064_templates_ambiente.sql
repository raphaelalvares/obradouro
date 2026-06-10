-- 0064_templates_ambiente.sql  (Livro de referências · Fatia 2 — Templates de ambiente + orçamento por cômodo)
-- Duas coisas:
--  (A) orcamento_itens ganha `ambiente` (texto, denormalizado como no checklist) → orçar POR CÔMODO
--      (pivot "por etapa | por cômodo", igual ao cronograma). NULL = obra geral (fundação, cobertura…).
--  (B) TEMPLATES de ambiente (nível-TENANT, biblioteca do arquiteto): uma "receita" por tipo×nível
--      ("Banheiro · alto padrão") que lista serviços do catálogo (0063) com regra de quantidade
--      (fixa OU por m²). Aplicar a um cômodo de área A gera as linhas do orçamento: qtd = por_area
--      ? fator×A : fator; subtotal = custo_unit × qtd (matemática no backend, fonte única).
--
-- LIÇÕES da revisão da Fatia 1 aplicadas aqui:
--  - created_by é `on delete set null` → o guard NÃO imutabiliza created_by (senão o SET NULL ao apagar
--    o profile dispararia o guard). Espelha 0062 ambientes.
--  - servico_id é `on delete CASCADE` (NÃO restrict): evita o landmine de FK ao apagar a conta. A
--    proteção "não excluir serviço em uso" é feita no SERVICE (catalogo.excluir checa uso → 409).
-- Aplicar como postgres. DEV antes de PROD.

begin;

-- ===================== (A) orçamento por cômodo =====================
-- Sem allowlist no orcamento_itens_guard (0060) → adicionar coluna é seguro (o guard só checa
-- identidade imutável + versão editável + arquiteto). NULL = sem cômodo (obra geral).
alter table public.orcamento_itens add column if not exists ambiente text;

-- ===================== (B1) ambiente_templates (receita: tipo × nível) =====================
create table if not exists public.ambiente_templates (
  id               uuid        primary key,                                       -- gerado no cliente
  tenant_id        uuid        not null references public.profiles(id) on delete cascade,
  tipo             text        not null,                                          -- "Banheiro", "Cozinha"…
  nivel            text        not null,                                          -- "Alto padrão", "Econômico"…
  tipo_norm        text        not null,                                          -- dedupe (norm_nome)
  nivel_norm       text        not null,
  area_referencia  numeric(10,2),                                                 -- "pensado p/ ~X m²" (informativo)
  ativo            boolean     not null default true,
  created_by       uuid        references public.profiles(id) on delete set null,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create unique index if not exists uq_ambiente_templates_tenant
  on public.ambiente_templates (tenant_id, tipo_norm, nivel_norm);
create index if not exists ix_ambiente_templates_tenant
  on public.ambiente_templates (tenant_id, ativo, tipo, nivel);
drop trigger if exists trg_ambiente_templates_updated_at on public.ambiente_templates;
create trigger trg_ambiente_templates_updated_at
  before update on public.ambiente_templates for each row execute function public.set_updated_at();

create or replace function public.ambiente_templates_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if new.tenant_id is distinct from (select auth.uid()) then
      raise exception 'tenant incoerente' using errcode = '42501';
    end if;
    return new;
  end if;
  if tg_op = 'UPDATE' then
    -- NÃO checar created_by (FK set null — ver cabeçalho). Identidade restante imutável.
    if new.id is distinct from old.id
       or new.tenant_id is distinct from old.tenant_id
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade do template e imutavel' using errcode = '42501';
    end if;
    return new;
  end if;
  return old;  -- DELETE
end;
$$;
alter function public.ambiente_templates_guard() owner to postgres;
drop trigger if exists trg_ambiente_templates_guard on public.ambiente_templates;
create trigger trg_ambiente_templates_guard
  before insert or update or delete on public.ambiente_templates
  for each row execute function public.ambiente_templates_guard();

-- ===================== (B2) ambiente_template_itens (linhas da receita) =====================
create table if not exists public.ambiente_template_itens (
  id           uuid          primary key,                                         -- gerado no cliente
  template_id  uuid          not null references public.ambiente_templates(id) on delete cascade,
  tenant_id    uuid          not null references public.profiles(id) on delete cascade,  -- denorm p/ RLS
  servico_id   uuid          not null references public.servicos_catalogo(id) on delete cascade,
  etapa        text,                                                              -- override de onde a linha cai
  por_area     boolean       not null default false,                             -- true: qtd = fator × área
  fator        numeric(14,4) not null default 1 check (fator >= 0),              -- fixa (por_area=false) ou coef/m²
  ordem        int           not null default 0,
  created_at   timestamptz   not null default now(),
  updated_at   timestamptz   not null default now()
);
create index if not exists ix_ambiente_template_itens_template
  on public.ambiente_template_itens (template_id, ordem);
create index if not exists ix_ambiente_template_itens_servico
  on public.ambiente_template_itens (servico_id);  -- p/ a checagem de uso em catalogo.excluir
drop trigger if exists trg_ambiente_template_itens_updated_at on public.ambiente_template_itens;
create trigger trg_ambiente_template_itens_updated_at
  before update on public.ambiente_template_itens for each row execute function public.set_updated_at();

create or replace function public.ambiente_template_itens_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'DELETE' then
    return old;  -- RLS já restringe ao próprio tenant
  end if;
  -- INSERT/UPDATE: tenant coerente + pai e serviço do MESMO tenant (FK não barra cross-tenant sozinha)
  if new.tenant_id is distinct from (select auth.uid()) then
    raise exception 'tenant incoerente' using errcode = '42501';
  end if;
  if not exists (select 1 from public.ambiente_templates t
                 where t.id = new.template_id and t.tenant_id = new.tenant_id) then
    raise exception 'template inexistente ou de outro tenant' using errcode = '42501';
  end if;
  if not exists (select 1 from public.servicos_catalogo s
                 where s.id = new.servico_id and s.tenant_id = new.tenant_id) then
    raise exception 'servico inexistente ou de outro tenant' using errcode = '42501';
  end if;
  if tg_op = 'UPDATE'
     and (new.id is distinct from old.id
          or new.template_id is distinct from old.template_id
          or new.tenant_id is distinct from old.tenant_id) then
    raise exception 'identidade do item e imutavel' using errcode = '42501';
  end if;
  return new;
end;
$$;
alter function public.ambiente_template_itens_guard() owner to postgres;
drop trigger if exists trg_ambiente_template_itens_guard on public.ambiente_template_itens;
create trigger trg_ambiente_template_itens_guard
  before insert or update or delete on public.ambiente_template_itens
  for each row execute function public.ambiente_template_itens_guard();

-- ===================== Grants + RLS self (espelha servicos_catalogo 0063) =====================
grant select, insert, update, delete on public.ambiente_templates      to cria_app;
grant select, insert, update, delete on public.ambiente_template_itens to cria_app;
alter table public.ambiente_templates      enable row level security;
alter table public.ambiente_template_itens enable row level security;

drop policy if exists ambiente_templates_select on public.ambiente_templates;
create policy ambiente_templates_select on public.ambiente_templates
  for select to authenticated using ( tenant_id = (select auth.uid()) );
drop policy if exists ambiente_templates_insert on public.ambiente_templates;
create policy ambiente_templates_insert on public.ambiente_templates
  for insert to authenticated with check ( tenant_id = (select auth.uid()) );
drop policy if exists ambiente_templates_update on public.ambiente_templates;
create policy ambiente_templates_update on public.ambiente_templates
  for update to authenticated
  using ( tenant_id = (select auth.uid()) ) with check ( tenant_id = (select auth.uid()) );
drop policy if exists ambiente_templates_delete on public.ambiente_templates;
create policy ambiente_templates_delete on public.ambiente_templates
  for delete to authenticated using ( tenant_id = (select auth.uid()) );

drop policy if exists ambiente_template_itens_select on public.ambiente_template_itens;
create policy ambiente_template_itens_select on public.ambiente_template_itens
  for select to authenticated using ( tenant_id = (select auth.uid()) );
drop policy if exists ambiente_template_itens_insert on public.ambiente_template_itens;
create policy ambiente_template_itens_insert on public.ambiente_template_itens
  for insert to authenticated with check ( tenant_id = (select auth.uid()) );
drop policy if exists ambiente_template_itens_update on public.ambiente_template_itens;
create policy ambiente_template_itens_update on public.ambiente_template_itens
  for update to authenticated
  using ( tenant_id = (select auth.uid()) ) with check ( tenant_id = (select auth.uid()) );
drop policy if exists ambiente_template_itens_delete on public.ambiente_template_itens;
create policy ambiente_template_itens_delete on public.ambiente_template_itens
  for delete to authenticated using ( tenant_id = (select auth.uid()) );

-- ===================== (C) RPC criar_orcamento_versao: clonar TAMBÉM o `ambiente` =====================
-- A RPC (0060) clona os itens da versão anterior com lista FIXA de colunas — sem `ambiente` ela nasceria
-- NULL na nova versão (perde o pivot por cômodo + quebra o dedupe do aplicar_template). Recriada aqui,
-- idêntica à 0060 + `ambiente`/`i.ambiente` no INSERT...SELECT do clone. Mantém owner/grants.
create or replace function public.criar_orcamento_versao(p_id uuid, p_projeto uuid)
returns table (id uuid, numero int, seq_humano bigint)
language plpgsql security definer set search_path = '' as $$
#variable_conflict use_column
declare
  v_uid    uuid := (select auth.uid());
  v_tenant uuid;
  v_numero int;
  v_atual  uuid;
  v_data date; v_val date; v_obs text;
  v_mmo numeric(6,3); v_mmat numeric(6,3); v_meq numeric(6,3); v_bdi numeric(6,3); v_imp numeric(6,3);
begin
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;
  if not public.is_arquiteto_ativo_projeto(p_projeto) then
    raise exception 'apenas arquiteto cria orcamento' using errcode = '42501';
  end if;
  select pj.tenant_id into v_tenant from public.projetos pj where pj.id = p_projeto;
  if v_tenant is null then
    raise exception 'projeto inexistente' using errcode = '23503';
  end if;

  -- idempotência offline por id (sem queimar seq)
  if exists (select 1 from public.orcamento_versoes v where v.id = p_id) then
    return query
      select v.id, v.numero, v.seq_humano
      from public.orcamento_versoes v where v.id = p_id and v.tenant_id = v_tenant;
    return;
  end if;

  perform pg_advisory_xact_lock(hashtext('cria:orcamento_versao'), hashtext(p_projeto::text));

  v_numero := coalesce(
    (select max(v.numero) from public.orcamento_versoes v where v.projeto_id = p_projeto), -1) + 1;
  select v.id into v_atual
    from public.orcamento_versoes v
    where v.projeto_id = p_projeto and v.congelado = false;

  if v_atual is not null then
    select v.data, v.validade, v.maj_mo, v.maj_material, v.maj_equipamento, v.bdi, v.imposto,
           v.observacoes
      into v_data, v_val, v_mmo, v_mmat, v_meq, v_bdi, v_imp, v_obs
      from public.orcamento_versoes v where v.id = v_atual;
    update public.orcamento_versoes set congelado = true where id = v_atual;
  else
    v_data := null; v_val := null; v_obs := null;
    v_mmo := 0; v_mmat := 0; v_meq := 0; v_bdi := 0; v_imp := 0;
  end if;

  begin
    insert into public.orcamento_versoes
      (id, projeto_id, tenant_id, numero, data, validade, maj_mo, maj_material, maj_equipamento,
       bdi, imposto, observacoes, created_by)
    values (p_id, p_projeto, v_tenant, v_numero, v_data, v_val, v_mmo, v_mmat, v_meq,
            v_bdi, v_imp, v_obs, v_uid);
  exception when unique_violation then
    return query
      select v.id, v.numero, v.seq_humano
      from public.orcamento_versoes v where v.id = p_id and v.tenant_id = v_tenant;
    return;
  end;

  if v_atual is not null then
    insert into public.orcamento_itens
      (id, versao_id, projeto_id, tenant_id, etapa, ordem_etapa, descricao, ordem,
       ambiente, unidade, quantidade, valor_mo, valor_material, valor_equipamento)
    select gen_random_uuid(), p_id, i.projeto_id, i.tenant_id, i.etapa, i.ordem_etapa, i.descricao,
           i.ordem, i.ambiente, i.unidade, i.quantidade, i.valor_mo, i.valor_material,
           i.valor_equipamento
    from public.orcamento_itens i where i.versao_id = v_atual;
  end if;

  return query
    select v.id, v.numero, v.seq_humano from public.orcamento_versoes v where v.id = p_id;
end;
$$;
alter function public.criar_orcamento_versao(uuid, uuid) owner to postgres;
revoke all on function public.criar_orcamento_versao(uuid, uuid) from public, anon;
grant execute on function public.criar_orcamento_versao(uuid, uuid) to authenticated;

commit;
