-- 0062_ambientes.sql  (Fatia A · parte 1 — Ambientes estruturados + pivot por cômodo)
-- Registro de AMBIENTES (cômodos) POR OBRA + checklist_itens.ambiente_id. ADITIVO: a coluna `ambiente`
-- (texto) FICA como nome denormalizado p/ display/PDF/CSV/import seguirem sem mudança; `ambiente_id`
-- liga o item ao registro (habilita pivot por cômodo, ordenação e área). O registro é auto-mantido
-- pelo backend a partir do texto (resolve-or-create por nome_norm). Aplicar como postgres. DEV antes de PROD.
--
-- NORM do ambiente = minúsculo + trim + colapsa espaços (SEM tirar acento). Difere do norm_nome de
-- etapas/itens (que tira acento via NFKD) DE PROPÓSITO: assim o backfill SQL casa EXATAMENTE com o
-- que o backend computa depois, sem depender da extensão unaccent (frágil no Supabase). Acentos são
-- preservados nos dois lados (consistente) — o custo é "Sótão"≠"sotao" não deduparem (caso raro).
-- O colapso de espaços usa a classe ASCII EXPLÍCITA [ \t\n\r\f\v] (NÃO \s): o \s do Postgres é
-- dependente de locale (colapsa/ignora NBSP etc. conforme LC_CTYPE) — o ASCII fixo é determinístico e
-- bate byte-a-byte com o _norm() do backend (ambientes.py), que usa a mesma classe.

begin;

-- ---------------------------------------------------------------------------------------------------
-- (1) Tabela de ambientes (registro por obra). SEM seq_humano (cômodo não é numerado pelo humano).
create table if not exists public.ambientes (
  id          uuid        primary key,
  obra_id     uuid        not null references public.obras(id)    on delete cascade,
  tenant_id   uuid        not null references public.profiles(id) on delete restrict,
  nome        text        not null,
  nome_norm   text        not null,           -- minúsculo+trim+colapsa-espaços (ver cabeçalho)
  ordem       int         not null default 0,
  area_m2     numeric(10,2),                   -- opcional (p/ futuro custo por m²)
  created_by  uuid        references public.profiles(id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create unique index if not exists uq_ambientes_obra_nomenorm on public.ambientes (obra_id, nome_norm);
create index if not exists ix_ambientes_obra_ordem on public.ambientes (obra_id, ordem, created_at);
drop trigger if exists trg_ambientes_updated_at on public.ambientes;
create trigger trg_ambientes_updated_at
  before update on public.ambientes for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------------------------------
-- (2) Vínculo no item (set null ao apagar o ambiente — o item não some).
alter table public.checklist_itens
  add column if not exists ambiente_id uuid references public.ambientes(id) on delete set null;
create index if not exists ix_itens_ambiente_id on public.checklist_itens (ambiente_id);

-- ---------------------------------------------------------------------------------------------------
-- (3) BACKFILL: cria 1 ambiente por nome distinto (norm simples) por obra e liga os itens. Roda ANTES
--     de criar o guard de ambientes (inserts passam livres) e com o guard do item DESLIGADO (o UPDATE
--     rodaria sob auth.uid()=null e seria barrado). Tudo na mesma transação.
alter table public.checklist_itens disable trigger trg_itens_guard;

with norm as (
  select i.obra_id,
         btrim(regexp_replace(i.ambiente, '[ \t\n\r\f\v]+', ' ', 'g'))        as nome,
         lower(btrim(regexp_replace(i.ambiente, '[ \t\n\r\f\v]+', ' ', 'g'))) as nn,
         i.ordem as it_ordem, i.created_at as it_created
  from public.checklist_itens i
  where i.ambiente is not null and btrim(i.ambiente) <> ''
),
grupos as (
  -- agrupa SÓ por (obra_id, nn) p/ casar com o unique uq_ambientes_obra_nomenorm; o tenant vem da
  -- obra (fonte-da-verdade), não do item, p/ não duplicar grupo se houver linha legada divergente.
  select obra_id, nn,
         (array_agg(nome order by it_ordem, it_created))[1] as nome,
         min(it_ordem) as min_ordem, min(it_created) as min_created
  from norm group by obra_id, nn
)
insert into public.ambientes (id, obra_id, tenant_id, nome, nome_norm, ordem)
select gen_random_uuid(), g.obra_id, o.tenant_id, g.nome, g.nn,
       (row_number() over (partition by g.obra_id order by g.min_ordem, g.min_created, g.nn)) - 1
from grupos g
join public.obras o on o.id = g.obra_id
on conflict (obra_id, nome_norm) do nothing;  -- idempotente: re-aplicar a migration é no-op no backfill

update public.checklist_itens i
set ambiente_id = a.id
from public.ambientes a
where a.obra_id = i.obra_id
  and a.nome_norm = lower(btrim(regexp_replace(i.ambiente, '[ \t\n\r\f\v]+', ' ', 'g')))
  and i.ambiente is not null and btrim(i.ambiente) <> ''
  and i.ambiente_id is null;

alter table public.checklist_itens enable trigger trg_itens_guard;

-- ---------------------------------------------------------------------------------------------------
-- (4) Guard de ambientes (SECURITY DEFINER, owner postgres): coerência tenant/obra, só arquiteto
--     escreve, identidade imutável. Criado DEPOIS do backfill (que insere sem auth.uid()).
create or replace function public.ambientes_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo(new.obra_id) then
      raise exception 'apenas arquiteto pode criar ambiente' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    if new.id is distinct from old.id
       or new.obra_id is distinct from old.obra_id
       or new.tenant_id is distinct from old.tenant_id
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade do ambiente e imutavel' using errcode = '42501';
    end if;
    if not public.is_arquiteto_ativo(old.obra_id) then
      raise exception 'apenas arquiteto pode alterar ambiente' using errcode = '42501';
    end if;
    return new;
  end if;

  -- DELETE
  if not public.is_arquiteto_ativo(old.obra_id) then
    raise exception 'apenas arquiteto pode remover ambiente' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.ambientes_guard() owner to postgres;
drop trigger if exists trg_ambientes_guard on public.ambientes;
create trigger trg_ambientes_guard
  before insert or update or delete on public.ambientes
  for each row execute function public.ambientes_guard();

-- ---------------------------------------------------------------------------------------------------
-- (5) Grants + RLS (espelha checklist 0024): SELECT p/ membro ativo; escrita só arquiteto.
grant select, insert, update, delete on public.ambientes to cria_app;
alter table public.ambientes enable row level security;

drop policy if exists ambientes_select on public.ambientes;
create policy ambientes_select on public.ambientes
  for select to authenticated
  using ( obra_id in (select public.current_obra_ids()) );

drop policy if exists ambientes_insert on public.ambientes;
create policy ambientes_insert on public.ambientes
  for insert to authenticated
  with check ( public.is_arquiteto_ativo(obra_id) );

drop policy if exists ambientes_update on public.ambientes;
create policy ambientes_update on public.ambientes
  for update to authenticated
  using      ( public.is_arquiteto_ativo(obra_id) )
  with check ( public.is_arquiteto_ativo(obra_id) );

drop policy if exists ambientes_delete on public.ambientes;
create policy ambientes_delete on public.ambientes
  for delete to authenticated
  using ( public.is_arquiteto_ativo(obra_id) );

commit;
