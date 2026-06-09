-- 0060_orcamento.sql  (Módulo de Orçamento, dentro de Projeto)
-- Um orçamento por projeto = o conjunto de VERSÕES do projeto (espelha o ciclo de revisões 0035/0040/
-- 0041). A versão NÃO-congelada é a editável (no máx. 1 por projeto); "Nova versão" congela a atual e
-- clona params+itens (numero R0, R1…). ARQUITETO-ONLY no v1 (RLS + service via projeto_writable);
-- cliente não vê. Custos por linha em 3 baldes (M.O/material/equipamento); preço calculado no backend:
--   Preço = [Σ subtotal_tipo × (1+majoração_tipo)] × (1+BDI) × (1+Imposto).
-- Itens: subtotais de linha (casam 1:1 com o import do Excel). Reusa is_arquiteto_ativo_projeto (0036),
-- set_updated_at, assign_entity_seq (0023).

-- ===================== ORCAMENTO_VERSOES =====================
create table if not exists public.orcamento_versoes (
  id              uuid        primary key,                                       -- gerado no cliente
  projeto_id      uuid        not null references public.projetos(id) on delete cascade,
  tenant_id       uuid        not null references public.profiles(id) on delete restrict,
  numero          int         not null,                                          -- R0..Rn (RPC sob lock)
  congelado       boolean     not null default false,                            -- true = superada (só-leitura)
  data            date,                                                          -- data do orçamento
  validade        date,                                                          -- validade da proposta
  enviado         boolean     not null default false,                            -- controle manual
  enviado_em      timestamptz,
  maj_mo          numeric(6,3) not null default 0,                               -- % majoração mão de obra
  maj_material    numeric(6,3) not null default 0,                               -- % majoração material
  maj_equipamento numeric(6,3) not null default 0,                              -- % majoração equipamento
  bdi             numeric(6,3) not null default 0,                               -- % BDI (engloba lucro/indiretos)
  imposto         numeric(6,3) not null default 0,                               -- % imposto
  observacoes     text,                                                          -- condições/pagamento
  seq_humano      bigint,                                                        -- trigger (abaixo)
  created_by      uuid        not null references public.profiles(id) on delete restrict,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create unique index if not exists uq_orcamento_versoes_projeto_numero on public.orcamento_versoes (projeto_id, numero);
create unique index if not exists uq_orcamento_versoes_tenant_seq on public.orcamento_versoes (tenant_id, seq_humano);
-- INVARIANTE: no máximo UMA versão editável (não-congelada) por projeto.
create unique index if not exists uq_orcamento_versao_editavel on public.orcamento_versoes (projeto_id) where congelado = false;
create index        if not exists ix_orcamento_versoes_projeto on public.orcamento_versoes (projeto_id, numero);

drop trigger if exists trg_orcamento_versoes_updated_at on public.orcamento_versoes;
create trigger trg_orcamento_versoes_updated_at
  before update on public.orcamento_versoes
  for each row execute function public.set_updated_at();

-- ===================== ORCAMENTO_ITENS =====================
create table if not exists public.orcamento_itens (
  id                uuid        primary key,                                     -- gerado no cliente/servidor
  versao_id         uuid        not null references public.orcamento_versoes(id) on delete cascade,
  projeto_id        uuid        not null references public.projetos(id) on delete cascade,  -- denorm p/ RLS
  tenant_id         uuid        not null references public.profiles(id) on delete restrict,
  etapa             text        not null,                                        -- grupo (ex.: "Demolição")
  ordem_etapa       int         not null default 0,
  descricao         text        not null,                                        -- serviço
  ordem             int         not null default 0,
  unidade           text,
  quantidade        numeric(14,3),
  valor_mo          numeric(14,2) not null default 0,                            -- subtotal linha M.O (R$)
  valor_material    numeric(14,2) not null default 0,                            -- subtotal linha material (R$)
  valor_equipamento numeric(14,2) not null default 0,                           -- subtotal linha equip. (R$)
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);

create index if not exists ix_orcamento_itens_versao on public.orcamento_itens (versao_id, ordem_etapa, ordem);

drop trigger if exists trg_orcamento_itens_updated_at on public.orcamento_itens;
create trigger trg_orcamento_itens_updated_at
  before update on public.orcamento_itens
  for each row execute function public.set_updated_at();

-- ===================== seq_humano (estende o contador genérico 0023/0046/0059) =====================
-- LISTA COMPLETA (CHECK é UM constraint): valores vigentes do 0059 + 'orcamento_versao'.
alter table public.entity_seq_counters
  drop constraint if exists entity_seq_counters_entity_type_check;
alter table public.entity_seq_counters
  drop constraint if exists entity_seq_counters_entity_type_chk;
alter table public.entity_seq_counters
  add  constraint entity_seq_counters_entity_type_chk
  check (entity_type in ('etapa', 'checklist_item', 'anexo', 'projeto', 'revisao',
                         'moodboard_item', 'nota_fiscal', 'oportunidade', 'orcamento_versao'));

-- ===================== GUARDS =====================
create or replace function public.orcamento_versoes_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.projetos pj
                   where pj.id = new.projeto_id and pj.tenant_id = new.tenant_id) then
      raise exception 'tenant/projeto incoerentes' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo_projeto(new.projeto_id) then
      raise exception 'apenas arquiteto cria orcamento' using errcode = '42501';
    end if;
    return new;
  end if;
  -- UPDATE: identidade IMUTÁVEL
  if new.id is distinct from old.id
     or new.tenant_id is distinct from old.tenant_id
     or new.projeto_id is distinct from old.projeto_id
     or new.numero is distinct from old.numero
     or new.created_at is distinct from old.created_at
     or new.created_by is distinct from old.created_by then
    raise exception 'identidade/numero da versao sao imutaveis' using errcode = '42501';
  end if;
  if not public.is_arquiteto_ativo_projeto(old.projeto_id) then
    raise exception 'apenas arquiteto altera o orcamento' using errcode = '42501';
  end if;
  -- versão CONGELADA é só-leitura (a única exceção é a própria transição false→true, abaixo)
  if old.congelado then
    raise exception 'versao congelada e somente leitura' using errcode = '42501';
  end if;
  if new.congelado is distinct from old.congelado and new.congelado = false then
    raise exception 'nao e possivel descongelar uma versao' using errcode = '42501';
  end if;
  return new;
end;
$$;
alter function public.orcamento_versoes_guard() owner to postgres;
drop trigger if exists trg_orcamento_versoes_guard on public.orcamento_versoes;
create trigger trg_orcamento_versoes_guard
  before insert or update on public.orcamento_versoes
  for each row execute function public.orcamento_versoes_guard();

create or replace function public.orcamento_itens_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  v_versao uuid := coalesce(new.versao_id, old.versao_id);
  v_projeto uuid := coalesce(new.projeto_id, old.projeto_id);
begin
  if not public.is_arquiteto_ativo_projeto(v_projeto) then
    raise exception 'apenas arquiteto edita o orcamento' using errcode = '42501';
  end if;
  -- a versão-pai tem de existir, ser do mesmo tenant/projeto e estar EDITÁVEL (não-congelada)
  if not exists (
       select 1 from public.orcamento_versoes v
       where v.id = v_versao and v.projeto_id = v_projeto and v.congelado = false) then
    raise exception 'versao inexistente ou congelada' using errcode = '42501';
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  if tg_op = 'UPDATE'
     and (new.id is distinct from old.id
          or new.versao_id is distinct from old.versao_id
          or new.tenant_id is distinct from old.tenant_id
          or new.projeto_id is distinct from old.projeto_id) then
    raise exception 'identidade do item e imutavel' using errcode = '42501';
  end if;
  return new;
end;
$$;
alter function public.orcamento_itens_guard() owner to postgres;
drop trigger if exists trg_orcamento_itens_guard on public.orcamento_itens;
create trigger trg_orcamento_itens_guard
  before insert or update or delete on public.orcamento_itens
  for each row execute function public.orcamento_itens_guard();

-- seq DEPOIS do guard ('trg_..._guard' < 'trg_..._seq')
drop trigger if exists trg_orcamento_versoes_seq on public.orcamento_versoes;
create trigger trg_orcamento_versoes_seq
  before insert on public.orcamento_versoes
  for each row execute function public.assign_entity_seq('orcamento_versao');

-- ===================== RPC: criar versão (R0 vazia; ou congela atual + clona) =====================
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
    -- clona params da atual e CONGELA a atual antes de inserir a nova (invariante 1 editável)
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
       unidade, quantidade, valor_mo, valor_material, valor_equipamento)
    select gen_random_uuid(), p_id, i.projeto_id, i.tenant_id, i.etapa, i.ordem_etapa, i.descricao,
           i.ordem, i.unidade, i.quantidade, i.valor_mo, i.valor_material, i.valor_equipamento
    from public.orcamento_itens i where i.versao_id = v_atual;
  end if;

  return query
    select v.id, v.numero, v.seq_humano from public.orcamento_versoes v where v.id = p_id;
end;
$$;
alter function public.criar_orcamento_versao(uuid, uuid) owner to postgres;
revoke all on function public.criar_orcamento_versao(uuid, uuid) from public, anon;
grant execute on function public.criar_orcamento_versao(uuid, uuid) to authenticated;

-- ===================== GRANTS + RLS (arquiteto-only no v1) =====================
grant select, insert, update          on public.orcamento_versoes to cria_app;  -- sem delete (cascade do projeto)
grant select, insert, update, delete  on public.orcamento_itens   to cria_app;

alter table public.orcamento_versoes enable row level security;
alter table public.orcamento_itens   enable row level security;

drop policy if exists orcamento_versoes_select on public.orcamento_versoes;
create policy orcamento_versoes_select on public.orcamento_versoes
  for select to authenticated
  using ( public.is_arquiteto_ativo_projeto(projeto_id) );
drop policy if exists orcamento_versoes_insert on public.orcamento_versoes;
create policy orcamento_versoes_insert on public.orcamento_versoes
  for insert to authenticated
  with check ( public.is_arquiteto_ativo_projeto(projeto_id) );
drop policy if exists orcamento_versoes_update on public.orcamento_versoes;
create policy orcamento_versoes_update on public.orcamento_versoes
  for update to authenticated
  using      ( public.is_arquiteto_ativo_projeto(projeto_id) )
  with check ( public.is_arquiteto_ativo_projeto(projeto_id) );

drop policy if exists orcamento_itens_select on public.orcamento_itens;
create policy orcamento_itens_select on public.orcamento_itens
  for select to authenticated
  using ( public.is_arquiteto_ativo_projeto(projeto_id) );
drop policy if exists orcamento_itens_insert on public.orcamento_itens;
create policy orcamento_itens_insert on public.orcamento_itens
  for insert to authenticated
  with check ( public.is_arquiteto_ativo_projeto(projeto_id) );
drop policy if exists orcamento_itens_update on public.orcamento_itens;
create policy orcamento_itens_update on public.orcamento_itens
  for update to authenticated
  using      ( public.is_arquiteto_ativo_projeto(projeto_id) )
  with check ( public.is_arquiteto_ativo_projeto(projeto_id) );
drop policy if exists orcamento_itens_delete on public.orcamento_itens;
create policy orcamento_itens_delete on public.orcamento_itens
  for delete to authenticated
  using ( public.is_arquiteto_ativo_projeto(projeto_id) );
