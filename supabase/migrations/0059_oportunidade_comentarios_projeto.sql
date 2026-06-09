-- 0059_oportunidade_comentarios_projeto.sql  (Comercial v2)
-- (1) COMENTÁRIOS por oportunidade: timeline de anotações da negociação (add/editar/excluir),
--     tenant-scoped (só o dono vê) — espelha o guard/RLS de oportunidades (0058). SEM seq_humano
--     (não tem rótulo humano). on delete cascade: some junto com a oportunidade.
-- (2) ELO com PROJETO: oportunidades.projeto_id (1:1 opcional) + guard estendido p/ coerência de tenant.
--     Costura a cadeia lead → projeto → obra (na conversão Ganho→obra o backend liga projeto↔obra).

-- ===================== (1) COMENTÁRIOS =====================
create table if not exists public.oportunidade_comentarios (
  id              uuid        primary key,                                       -- gerado no cliente
  oportunidade_id uuid        not null references public.oportunidades(id) on delete cascade,
  tenant_id       uuid        not null references public.profiles(id) on delete restrict,
  texto           text        not null,
  created_by      uuid        not null references public.profiles(id) on delete restrict,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

create index if not exists ix_oport_coment_op on public.oportunidade_comentarios (oportunidade_id, created_at);

drop trigger if exists trg_oport_coment_updated_at on public.oportunidade_comentarios;
create trigger trg_oport_coment_updated_at
  before update on public.oportunidade_comentarios
  for each row execute function public.set_updated_at();

-- guard: imutável id/oportunidade/tenant/created_*; texto editável; dono = auth.uid; na inserção a
-- oportunidade tem de pertencer ao tenant. (RLS é a 2ª camada; aqui fica a regra fina.)
create or replace function public.oportunidade_comentarios_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if new.tenant_id is distinct from (select auth.uid()) then
      raise exception 'comentario pertence a outro tenant' using errcode = '42501';
    end if;
    if not exists (
         select 1 from public.oportunidades o
         where o.id = new.oportunidade_id and o.tenant_id = new.tenant_id) then
      raise exception 'oportunidade nao pertence ao tenant do comentario' using errcode = '42501';
    end if;
    return new;
  end if;
  if tg_op = 'DELETE' then
    if old.tenant_id is distinct from (select auth.uid()) then
      raise exception 'apenas o dono remove o comentario' using errcode = '42501';
    end if;
    return old;
  end if;
  -- UPDATE
  if new.id is distinct from old.id
     or new.oportunidade_id is distinct from old.oportunidade_id
     or new.tenant_id is distinct from old.tenant_id
     or new.created_by is distinct from old.created_by
     or new.created_at is distinct from old.created_at then
    raise exception 'identidade do comentario e imutavel' using errcode = '42501';
  end if;
  if old.tenant_id is distinct from (select auth.uid()) then
    raise exception 'apenas o dono altera o comentario' using errcode = '42501';
  end if;
  return new;
end;
$$;
alter function public.oportunidade_comentarios_guard() owner to postgres;
drop trigger if exists trg_oport_coment_guard on public.oportunidade_comentarios;
create trigger trg_oport_coment_guard
  before insert or update or delete on public.oportunidade_comentarios
  for each row execute function public.oportunidade_comentarios_guard();

grant select, insert, update, delete on public.oportunidade_comentarios to cria_app;

alter table public.oportunidade_comentarios enable row level security;

drop policy if exists oport_coment_select on public.oportunidade_comentarios;
create policy oport_coment_select on public.oportunidade_comentarios
  for select to authenticated
  using ( tenant_id = (select auth.uid()) );
drop policy if exists oport_coment_insert on public.oportunidade_comentarios;
create policy oport_coment_insert on public.oportunidade_comentarios
  for insert to authenticated
  with check ( tenant_id = (select auth.uid()) );
drop policy if exists oport_coment_update on public.oportunidade_comentarios;
create policy oport_coment_update on public.oportunidade_comentarios
  for update to authenticated
  using      ( tenant_id = (select auth.uid()) )
  with check ( tenant_id = (select auth.uid()) );
drop policy if exists oport_coment_delete on public.oportunidade_comentarios;
create policy oport_coment_delete on public.oportunidade_comentarios
  for delete to authenticated
  using ( tenant_id = (select auth.uid()) );

-- ===================== (2) ELO COM PROJETO =====================
alter table public.oportunidades
  add column if not exists projeto_id uuid references public.projetos(id) on delete set null;
-- 1 projeto origina-se de no MÁXIMO 1 oportunidade (parcial: NULL é o caso comum até vincular).
create unique index if not exists uq_oportunidades_projeto
  on public.oportunidades (projeto_id) where projeto_id is not null;

-- Recria o guard (0058) ADICIONANDO as checagens de projeto_id (espelham as de obra_id).
create or replace function public.oportunidades_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if new.tenant_id is distinct from (select auth.uid()) then
      raise exception 'oportunidade pertence a outro tenant' using errcode = '42501';
    end if;
    if new.obra_id is not null and not exists (
         select 1 from public.obras o where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'obra vinculada nao pertence ao tenant da oportunidade' using errcode = '42501';
    end if;
    if new.projeto_id is not null and not exists (
         select 1 from public.projetos p where p.id = new.projeto_id and p.tenant_id = new.tenant_id) then
      raise exception 'projeto vinculado nao pertence ao tenant da oportunidade' using errcode = '42501';
    end if;
    return new;
  end if;
  -- UPDATE: identidade IMUTÁVEL
  if new.id is distinct from old.id
     or new.tenant_id is distinct from old.tenant_id
     or new.created_by is distinct from old.created_by
     or new.created_at is distinct from old.created_at then
    raise exception 'identidade da oportunidade e imutavel' using errcode = '42501';
  end if;
  if old.tenant_id is distinct from (select auth.uid()) then
    raise exception 'apenas o dono altera a oportunidade' using errcode = '42501';
  end if;
  -- vincular/trocar obra: a obra NOVA tem de ser do MESMO tenant (anti cross-tenant)
  if new.obra_id is not null and new.obra_id is distinct from old.obra_id and not exists (
       select 1 from public.obras o where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
    raise exception 'obra vinculada nao pertence ao tenant da oportunidade' using errcode = '42501';
  end if;
  -- vincular/trocar projeto: idem
  if new.projeto_id is not null and new.projeto_id is distinct from old.projeto_id and not exists (
       select 1 from public.projetos p where p.id = new.projeto_id and p.tenant_id = new.tenant_id) then
    raise exception 'projeto vinculado nao pertence ao tenant da oportunidade' using errcode = '42501';
  end if;
  return new;
end;
$$;
alter function public.oportunidades_guard() owner to postgres;
-- (trigger trg_oportunidades_guard já existe do 0058; create or replace na função basta.)
