-- 0066_acompanhamento.sql  (Fatia C — Acompanhamento da obra)
-- Três frentes: DIÁRIO DE OBRA (relato datado, com fotos), PENDÊNCIAS / punch list (defeitos a
-- resolver, com fotos) e AVANÇO FÍSICO/curva S (derivado do checklist — sem tabela, calculado no
-- backend). Aqui vêm as DUAS tabelas + o seq + guards + RLS, e a extensão do módulo de ANEXOS
-- (polimórfico) p/ aceitar 'diario' e 'pendencia' como donos de foto. Aplicar como postgres. DEV→PROD.
--
-- Papéis (espelha anexos/checklist): quem EXECUTA a obra (arquiteto OU prestador) escreve; cliente é
-- read-only. Identidade imutável; created_by NÃO é imutabilizado (FK on delete set null — um SET NULL
-- ao apagar o profile dispararia o guard; lição das 0062/0063/0065). Dual-ID (uuid cliente + seq tenant).

begin;

-- ===================================================================================================
-- (1) DIÁRIO DE OBRA — relato datado da execução. Vários por dia (visitas diferentes) → sem unique.
create table if not exists public.diario_obra (
  id          uuid        primary key,
  obra_id     uuid        not null references public.obras(id)    on delete cascade,
  tenant_id   uuid        not null references public.profiles(id) on delete restrict,
  data        date        not null,
  clima       text,                                              -- livre (ex.: "Sol", "Chuva")
  efetivo     int         check (efetivo is null or efetivo >= 0),  -- nº de pessoas no canteiro
  texto       text        not null,
  seq_humano  bigint,
  created_by  uuid        references public.profiles(id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create unique index if not exists uq_diario_tenant_seq on public.diario_obra (tenant_id, seq_humano);
create index if not exists ix_diario_obra_data on public.diario_obra (obra_id, data desc, created_at desc);
drop trigger if exists trg_diario_obra_updated_at on public.diario_obra;
create trigger trg_diario_obra_updated_at
  before update on public.diario_obra for each row execute function public.set_updated_at();

-- ===================================================================================================
-- (2) PENDÊNCIAS / punch list — defeitos/itens a resolver. ambiente_id (onde, opcional, mesma obra) +
--     equipe_id (responsável, opcional, biblioteca nível-tenant). Status binário aberta/resolvida.
create table if not exists public.pendencias (
  id            uuid        primary key,
  obra_id       uuid        not null references public.obras(id)     on delete cascade,
  tenant_id     uuid        not null references public.profiles(id)  on delete restrict,
  descricao     text        not null,
  ambiente_id   uuid        references public.ambientes(id) on delete set null,
  equipe_id     uuid        references public.equipes(id)   on delete set null,
  prioridade    text        not null default 'media' check (prioridade in ('baixa','media','alta')),
  status        text        not null default 'aberta' check (status in ('aberta','resolvida')),
  resolvido_por uuid        references public.profiles(id) on delete set null,
  resolvido_em  timestamptz,
  seq_humano    bigint,
  created_by    uuid        references public.profiles(id) on delete set null,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create unique index if not exists uq_pendencias_tenant_seq on public.pendencias (tenant_id, seq_humano);
create index if not exists ix_pendencias_obra
  on public.pendencias (obra_id, status, prioridade, created_at desc);
drop trigger if exists trg_pendencias_updated_at on public.pendencias;
create trigger trg_pendencias_updated_at
  before update on public.pendencias for each row execute function public.set_updated_at();

-- ===================================================================================================
-- (3) SEQ humano por tenant — reusa entity_seq_counters + assign_entity_seq() (0023). Estende o CHECK
--     com 'diario' e 'pendencia' (lista COMPLETA + as 2 novas; drop+add => re-aplicável).
alter table public.entity_seq_counters
  drop constraint if exists entity_seq_counters_entity_type_check;
alter table public.entity_seq_counters
  drop constraint if exists entity_seq_counters_entity_type_chk;
alter table public.entity_seq_counters
  add  constraint entity_seq_counters_entity_type_chk
  check (entity_type in ('etapa', 'checklist_item', 'anexo', 'projeto', 'revisao',
                         'moodboard_item', 'nota_fiscal', 'oportunidade', 'orcamento_versao',
                         'diario', 'pendencia'));

drop trigger if exists trg_diario_obra_seq on public.diario_obra;
create trigger trg_diario_obra_seq
  before insert on public.diario_obra for each row execute function public.assign_entity_seq('diario');

drop trigger if exists trg_pendencias_seq on public.pendencias;
create trigger trg_pendencias_seq
  before insert on public.pendencias for each row execute function public.assign_entity_seq('pendencia');

-- ===================================================================================================
-- (4) GUARDS (SECURITY DEFINER, owner postgres). Disparam ANTES do seq (nome '_guard' < '_seq').
-- ---------------------------------------------------------------------------------------------------
-- Diário: INSERT por quem executa; editar/apagar = arquiteto (qualquer) OU autor (prestador, o próprio).
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
drop trigger if exists trg_diario_obra_guard on public.diario_obra;
create trigger trg_diario_obra_guard
  before insert or update or delete on public.diario_obra
  for each row execute function public.diario_obra_guard();

-- ---------------------------------------------------------------------------------------------------
-- Pendências: INSERT por quem executa; coerência de ambiente_id (mesma obra) e equipe_id (mesmo
-- tenant). UPDATE: arquiteto edita tudo; prestador SÓ resolve (allowlist status/resolvido_*); cliente
-- nada. DELETE: arquiteto qualquer; prestador a própria.
create or replace function public.pendencias_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    if new.ambiente_id is not null
       and not exists (select 1 from public.ambientes a
                       where a.id = new.ambiente_id and a.obra_id = new.obra_id) then
      raise exception 'ambiente nao pertence a obra' using errcode = '23514';
    end if;
    if new.equipe_id is not null
       and not exists (select 1 from public.equipes eq
                       where eq.id = new.equipe_id and eq.tenant_id = new.tenant_id) then
      raise exception 'equipe de outro tenant' using errcode = '42501';
    end if;
    if not public.pode_executar_obra(new.obra_id) then
      raise exception 'apenas quem executa a obra abre pendencia' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    if new.id is distinct from old.id
       or new.obra_id is distinct from old.obra_id
       or new.tenant_id is distinct from old.tenant_id
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade da pendencia e imutavel' using errcode = '42501';
    end if;
    if new.ambiente_id is not null and new.ambiente_id is distinct from old.ambiente_id
       and not exists (select 1 from public.ambientes a
                       where a.id = new.ambiente_id and a.obra_id = new.obra_id) then
      raise exception 'ambiente nao pertence a obra' using errcode = '23514';
    end if;
    if new.equipe_id is not null and new.equipe_id is distinct from old.equipe_id
       and not exists (select 1 from public.equipes eq
                       where eq.id = new.equipe_id and eq.tenant_id = new.tenant_id) then
      raise exception 'equipe de outro tenant' using errcode = '42501';
    end if;
    v_papel := public.meu_papel_obra(old.obra_id);
    if v_papel = 'arquiteto' then
      return new;
    elsif v_papel = 'prestador' then
      -- ALLOWLIST: prestador só RESOLVE (status + carimbo) — não mexe em descrição/prioridade/onde/quem.
      if (to_jsonb(new) - 'status' - 'resolvido_por' - 'resolvido_em' - 'updated_at')
         is distinct from
         (to_jsonb(old) - 'status' - 'resolvido_por' - 'resolvido_em' - 'updated_at')
      then
        raise exception 'prestador so pode resolver/reabrir a pendencia' using errcode = '42501';
      end if;
      return new;
    else
      raise exception 'sem permissao para alterar pendencia' using errcode = '42501';
    end if;
  end if;

  -- DELETE
  v_papel := public.meu_papel_obra(old.obra_id);
  if v_papel = 'arquiteto' then
    return old;
  elsif v_papel = 'prestador' and old.created_by is not distinct from (select auth.uid()) then
    return old;
  else
    raise exception 'sem permissao para apagar pendencia' using errcode = '42501';
  end if;
end;
$$;
alter function public.pendencias_guard() owner to postgres;
drop trigger if exists trg_pendencias_guard on public.pendencias;
create trigger trg_pendencias_guard
  before insert or update or delete on public.pendencias
  for each row execute function public.pendencias_guard();

-- ===================================================================================================
-- (5) GRANTS + RLS (espelha checklist/anexos): SELECT p/ membro ativo; escrita p/ quem executa.
grant select, insert, update, delete on public.diario_obra to cria_app;
grant select, insert, update, delete on public.pendencias  to cria_app;
alter table public.diario_obra enable row level security;
alter table public.pendencias  enable row level security;

drop policy if exists diario_select on public.diario_obra;
create policy diario_select on public.diario_obra
  for select to authenticated using ( obra_id in (select public.current_obra_ids()) );
drop policy if exists diario_insert on public.diario_obra;
create policy diario_insert on public.diario_obra
  for insert to authenticated with check ( public.pode_executar_obra(obra_id) );
drop policy if exists diario_update on public.diario_obra;
create policy diario_update on public.diario_obra
  for update to authenticated
  using ( public.pode_executar_obra(obra_id) ) with check ( public.pode_executar_obra(obra_id) );
drop policy if exists diario_delete on public.diario_obra;
create policy diario_delete on public.diario_obra
  for delete to authenticated using ( public.pode_executar_obra(obra_id) );

drop policy if exists pendencias_select on public.pendencias;
create policy pendencias_select on public.pendencias
  for select to authenticated using ( obra_id in (select public.current_obra_ids()) );
drop policy if exists pendencias_insert on public.pendencias;
create policy pendencias_insert on public.pendencias
  for insert to authenticated with check ( public.pode_executar_obra(obra_id) );
drop policy if exists pendencias_update on public.pendencias;
create policy pendencias_update on public.pendencias
  for update to authenticated
  using ( public.pode_executar_obra(obra_id) ) with check ( public.pode_executar_obra(obra_id) );
drop policy if exists pendencias_delete on public.pendencias;
create policy pendencias_delete on public.pendencias
  for delete to authenticated using ( public.pode_executar_obra(obra_id) );

-- ===================================================================================================
-- (6) ANEXOS polimórficos p/ as fotos do diário e da pendência. Estende o CHECK do parent_type, recria
--     o anexos_guard (0031) adicionando os 2 ramos de coerência, e liga a limpeza de órfãos (0032)
--     nas 2 tabelas (apagar 1 entrada some as fotos dela; a FK obra_id já cobre apagar a obra inteira).
alter table public.anexos drop constraint if exists anexos_parent_type_check;
alter table public.anexos
  add constraint anexos_parent_type_check
  check (parent_type in ('etapa', 'checklist_item', 'diario', 'pendencia'));

create or replace function public.anexos_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    if new.parent_type = 'etapa' then
      if not exists (select 1 from public.etapas e
                     where e.id = new.parent_id and e.obra_id = new.obra_id) then
        raise exception 'etapa do anexo nao pertence a obra' using errcode = '23514';
      end if;
    elsif new.parent_type = 'checklist_item' then
      if not exists (select 1 from public.checklist_itens i
                     where i.id = new.parent_id and i.obra_id = new.obra_id) then
        raise exception 'item do anexo nao pertence a obra' using errcode = '23514';
      end if;
    elsif new.parent_type = 'diario' then
      if not exists (select 1 from public.diario_obra d
                     where d.id = new.parent_id and d.obra_id = new.obra_id) then
        raise exception 'diario do anexo nao pertence a obra' using errcode = '23514';
      end if;
    elsif new.parent_type = 'pendencia' then
      if not exists (select 1 from public.pendencias p
                     where p.id = new.parent_id and p.obra_id = new.obra_id) then
        raise exception 'pendencia do anexo nao pertence a obra' using errcode = '23514';
      end if;
    else
      raise exception 'parent_type invalido' using errcode = '23514';
    end if;
    if not public.pode_executar_obra(new.obra_id) then
      raise exception 'apenas quem executa a obra pode anexar' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    raise exception 'anexo e imutavel (apague e suba outro)' using errcode = '42501';
  end if;

  -- DELETE
  v_papel := public.meu_papel_obra(old.obra_id);
  if v_papel = 'arquiteto' then
    return old;
  elsif v_papel = 'prestador' then
    if old.criado_por is distinct from (select auth.uid()) then
      raise exception 'prestador so apaga o proprio anexo' using errcode = '42501';
    end if;
    return old;
  else
    raise exception 'sem permissao para apagar anexo' using errcode = '42501';
  end if;
end;
$$;
alter function public.anexos_guard() owner to postgres;
-- trigger trg_anexos_guard (0031) já aponta p/ esta função; não recriar.

drop trigger if exists trg_diario_anexos_cleanup on public.diario_obra;
create trigger trg_diario_anexos_cleanup
  after delete on public.diario_obra
  for each row execute function public.anexos_limpar_orfaos('diario');

drop trigger if exists trg_pendencias_anexos_cleanup on public.pendencias;
create trigger trg_pendencias_anexos_cleanup
  after delete on public.pendencias
  for each row execute function public.anexos_limpar_orfaos('pendencia');

commit;
