-- 0087_oportunidade_contexto.sql  (Comercial — "cartão de contexto" do cliente, 1:1 com a oportunidade)
-- Memória estruturada do cliente para o agente de lembretes: um PERFIL (jsonb: canal preferido, melhor
-- horário, cadência de follow-up, decisor, sensível a preço) que regras/automação leem + um RESUMO
-- curto (texto, o "claude.md" do cliente; o teto de tamanho é aplicado no app). 1:1 com a oportunidade
-- (PK = oportunidade_id; on delete cascade). NÃO há entidade "cliente" hoje, então o contexto mora na
-- oportunidade. TENANT-scoped (só o dono/arquiteto) — espelha o guard/RLS de oportunidade_comentarios
-- (0059): cinto-e-suspensório (RLS é a 2ª camada; o guard fecha imutabilidade + coerência de tenant).
-- Aplicar como postgres, DEPOIS da 0086. DEV antes de PROD.

create table if not exists public.oportunidade_contexto (
  oportunidade_id uuid        primary key references public.oportunidades(id) on delete cascade,
  tenant_id       uuid        not null references public.profiles(id) on delete restrict,
  perfil          jsonb       not null default '{}'::jsonb,   -- estruturado (canal, horário, cadência…)
  resumo          text,                                       -- "cartão de contexto" curto (cap no app)
  updated_by      uuid        references public.profiles(id) on delete set null,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

drop trigger if exists trg_oport_contexto_updated_at on public.oportunidade_contexto;
create trigger trg_oport_contexto_updated_at
  before update on public.oportunidade_contexto
  for each row execute function public.set_updated_at();

-- guard (camada 2): dono = auth.uid; identidade imutável; na inserção a oportunidade é do tenant.
create or replace function public.oportunidade_contexto_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if new.tenant_id is distinct from (select auth.uid()) then
      raise exception 'contexto pertence a outro tenant' using errcode = '42501';
    end if;
    if not exists (
         select 1 from public.oportunidades o
         where o.id = new.oportunidade_id and o.tenant_id = new.tenant_id) then
      raise exception 'oportunidade nao pertence ao tenant do contexto' using errcode = '42501';
    end if;
    return new;
  end if;
  if tg_op = 'DELETE' then
    if old.tenant_id is distinct from (select auth.uid()) then
      raise exception 'apenas o dono remove o contexto' using errcode = '42501';
    end if;
    return old;
  end if;
  -- UPDATE: identidade IMUTÁVEL
  if new.oportunidade_id is distinct from old.oportunidade_id
     or new.tenant_id is distinct from old.tenant_id
     or new.created_at is distinct from old.created_at then
    raise exception 'identidade do contexto e imutavel' using errcode = '42501';
  end if;
  if old.tenant_id is distinct from (select auth.uid()) then
    raise exception 'apenas o dono altera o contexto' using errcode = '42501';
  end if;
  return new;
end;
$$;
alter function public.oportunidade_contexto_guard() owner to postgres;
drop trigger if exists trg_oport_contexto_guard on public.oportunidade_contexto;
create trigger trg_oport_contexto_guard
  before insert or update or delete on public.oportunidade_contexto
  for each row execute function public.oportunidade_contexto_guard();

grant select, insert, update, delete on public.oportunidade_contexto to cria_app;

alter table public.oportunidade_contexto enable row level security;

drop policy if exists oport_contexto_select on public.oportunidade_contexto;
create policy oport_contexto_select on public.oportunidade_contexto
  for select to authenticated
  using ( tenant_id = (select auth.uid()) );
drop policy if exists oport_contexto_insert on public.oportunidade_contexto;
create policy oport_contexto_insert on public.oportunidade_contexto
  for insert to authenticated
  with check ( tenant_id = (select auth.uid()) );
drop policy if exists oport_contexto_update on public.oportunidade_contexto;
create policy oport_contexto_update on public.oportunidade_contexto
  for update to authenticated
  using      ( tenant_id = (select auth.uid()) )
  with check ( tenant_id = (select auth.uid()) );
drop policy if exists oport_contexto_delete on public.oportunidade_contexto;
create policy oport_contexto_delete on public.oportunidade_contexto
  for delete to authenticated
  using ( tenant_id = (select auth.uid()) );
