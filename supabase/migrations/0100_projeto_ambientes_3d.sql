-- 0100_projeto_ambientes_3d.sql  (leva 2 do portal — 3D/APROVAÇÃO POR AMBIENTE, nível de PROJETO)
--
-- A etapa `projeto_3d` (0097) ganha CÔMODOS do projeto: o arquiteto cadastra os ambientes, sobe os
-- renders/links 3D de cada um (material por cômodo) e ENVIA p/ aprovação; o cliente APROVA ou PEDE
-- ALTERAÇÃO cômodo a cômodo. A tabela `ambientes` (0062) é OBRA-bound (FK a obras) → não serve p/
-- projeto (projeto pode existir sem obra). Esta tabela ESPELHA o guard+RLS do 0062, mas a nível de
-- PROJETO e SEM o denorm/backfill de checklist_itens (ambientes de projeto são isolados).
--
-- Estado ÚNICO que recicla por cômodo (decisão do usuário; NÃO rodadas numeradas):
--   rascunho → pendente → aprovado | alteracao_pedida; ao pedir alteração o arquiteto sobe novos
--   renders e REENVIA → volta a pendente. Histórico fica no audit log (core).
--
-- O guard espelha o ramo arquiteto/cliente + o carimbo M9 do `revisoes_guard` (0098): a DECISÃO 3D
-- (status aprovado/alteracao_pedida + decidido_por/em) é SEMPRE do cliente e carimbada pelo servidor
-- (infalsificável via PostgREST direto). O material 3D mora em `projeto_etapa_anexos` (0099) + a coluna
-- nova `ambiente_id` — reusa todo o pipeline de mídia (imutável, bytes no StorageBackend), sem tabela
-- nova. Depende de 0097 (etapa_projeto/projeto_etapas), 0099 (projeto_etapa_anexos) e 0036/0096
-- (is_arquiteto_ativo_projeto / current_projeto_ids / meu_papel_projeto, já expiry-aware).
-- Aplicar como postgres, após 0099. DEV antes de PROD. Lição citext: nada de citext sob search_path=''
-- (não há e-mail aqui).

begin;

-- ===================== (1) enum do estado 3D (idempotente) =====================
do $$
begin
  if not exists (
    select 1 from pg_type where typname = 'status_aprovacao_3d'
      and typnamespace = 'public'::regnamespace
  ) then
    create type public.status_aprovacao_3d as enum
      ('rascunho', 'pendente', 'aprovado', 'alteracao_pedida');
  end if;
end $$;

-- ===================== (2) tabela de cômodos do projeto (carrega o estado 3D) =====================
create table if not exists public.projeto_ambientes (
  id              uuid        primary key,                              -- gerado no cliente (dual-ID)
  projeto_id      uuid        not null references public.projetos(id)  on delete cascade,
  tenant_id       uuid        not null references public.profiles(id)  on delete restrict,
  nome            text        not null,
  nome_norm       text        not null,            -- minúsculo+trim+colapsa-espaços (≠ unaccent; ver 0062)
  ordem           int         not null default 0,
  -- estado da aprovação 3D (estado único que recicla):
  status_3d       public.status_aprovacao_3d not null default 'rascunho',
  motivo_3d       text,                            -- preenchido pelo cliente ao pedir alteração
  decidido_por_3d uuid        references public.profiles(id) on delete set null,  -- carimbo M9
  decidido_em_3d  timestamptz,
  created_by      uuid        references public.profiles(id) on delete set null,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create unique index if not exists uq_projeto_ambientes_projnome
  on public.projeto_ambientes (projeto_id, nome_norm);
create index if not exists ix_projeto_ambientes_proj_ordem
  on public.projeto_ambientes (projeto_id, ordem, created_at);
drop trigger if exists trg_projeto_ambientes_updated_at on public.projeto_ambientes;
create trigger trg_projeto_ambientes_updated_at
  before update on public.projeto_ambientes for each row execute function public.set_updated_at();

-- ===================== (3) guard (espelha ambientes_guard + revisoes_guard M9) =====================
create or replace function public.projeto_ambientes_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.projetos pj
                   where pj.id = new.projeto_id and pj.tenant_id = new.tenant_id) then
      raise exception 'tenant/projeto incoerentes' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo_projeto(new.projeto_id) then
      raise exception 'apenas arquiteto cria comodo' using errcode = '42501';
    end if;
    if new.status_3d <> 'rascunho' then  -- cômodo nasce em rascunho (poka-yoke)
      raise exception 'comodo nasce em rascunho' using errcode = '23514';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    -- identidade imutável p/ todos (inclui created_by — autoria não se reescreve; espelha 0098)
    if new.id is distinct from old.id
       or new.projeto_id is distinct from old.projeto_id
       or new.tenant_id is distinct from old.tenant_id
       or new.created_by is distinct from old.created_by
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade do comodo e imutavel' using errcode = '42501';
    end if;
    v_papel := public.meu_papel_projeto(old.projeto_id);
    if v_papel = 'arquiteto' then
      if new.status_3d is distinct from old.status_3d then
        -- arquiteto só ENVIA (→pendente) ou RECOLHE (→rascunho); a aprovação é verbo do cliente
        if new.status_3d not in ('rascunho', 'pendente') then
          raise exception 'arquiteto so envia (pendente) ou recolhe (rascunho)' using errcode = '42501';
        end if;
        -- ciclo fresco: zera a decisão anterior do cliente (servidor)
        new.motivo_3d := null;
        new.decidido_por_3d := null;
        new.decidido_em_3d := null;
      else
        -- status inalterado (rename/reordenar): arquiteto NÃO mexe na decisão do cliente
        if new.motivo_3d is distinct from old.motivo_3d
           or new.decidido_por_3d is distinct from old.decidido_por_3d
           or new.decidido_em_3d is distinct from old.decidido_em_3d then
          raise exception 'a decisao 3d e do cliente' using errcode = '42501';
        end if;
      end if;
      return new;
    elsif v_papel = 'cliente' then
      if old.status_3d <> 'pendente' then
        raise exception '3d nao esta em aprovacao' using errcode = '42501';
      end if;
      if new.nome is distinct from old.nome
         or new.nome_norm is distinct from old.nome_norm
         or new.ordem is distinct from old.ordem then
        raise exception 'cliente nao edita o comodo' using errcode = '42501';
      end if;
      if new.status_3d not in ('aprovado', 'alteracao_pedida') then
        raise exception 'transicao de status invalida' using errcode = '42501';
      end if;
      if new.status_3d = 'alteracao_pedida'
         and (new.motivo_3d is null or btrim(new.motivo_3d) = '') then
        raise exception 'pedir alteracao exige motivo' using errcode = '23514';
      end if;
      if new.status_3d = 'aprovado' then
        new.motivo_3d := null;  -- aprovação não guarda motivo
      end if;
      -- M9: a decisão é SEMPRE carimbada pelo servidor (cliente não forja quem/quando)
      new.decidido_por_3d := (select auth.uid());
      new.decidido_em_3d := now();
      return new;
    else
      raise exception 'sem permissao no comodo' using errcode = '42501';
    end if;
  end if;

  -- DELETE
  if not public.is_arquiteto_ativo_projeto(old.projeto_id) then
    raise exception 'apenas arquiteto remove comodo' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.projeto_ambientes_guard() owner to postgres;
drop trigger if exists trg_projeto_ambientes_guard on public.projeto_ambientes;
create trigger trg_projeto_ambientes_guard
  before insert or update or delete on public.projeto_ambientes
  for each row execute function public.projeto_ambientes_guard();

-- ===================== (4) grants + RLS (espelha revisoes/0039) =====================
-- Cliente LÊ (timeline do portal) e DECIDE (update); só o arquiteto cria/edita/remove. O guard refina
-- papel/coluna/transição em cada UPDATE.
grant select, insert, update, delete on public.projeto_ambientes to cria_app;
alter table public.projeto_ambientes enable row level security;

drop policy if exists projeto_ambientes_select on public.projeto_ambientes;
create policy projeto_ambientes_select on public.projeto_ambientes
  for select to authenticated
  using ( tenant_id = (select auth.uid())
          or projeto_id in (select public.current_projeto_ids()) );

drop policy if exists projeto_ambientes_insert on public.projeto_ambientes;
create policy projeto_ambientes_insert on public.projeto_ambientes
  for insert to authenticated
  with check ( tenant_id = (select auth.uid())
               and public.is_arquiteto_ativo_projeto(projeto_id) );

drop policy if exists projeto_ambientes_update on public.projeto_ambientes;
create policy projeto_ambientes_update on public.projeto_ambientes
  for update to authenticated
  using      ( projeto_id in (select public.current_projeto_ids()) )
  with check ( projeto_id in (select public.current_projeto_ids()) );

drop policy if exists projeto_ambientes_delete on public.projeto_ambientes;
create policy projeto_ambientes_delete on public.projeto_ambientes
  for delete to authenticated
  using ( public.is_arquiteto_ativo_projeto(projeto_id) );

-- ===================== (5) material 3D por cômodo: ambiente_id em projeto_etapa_anexos =====================
-- ADD COLUMN puro: o projeto_etapa_anexos_guard (0099, imutável-no-update, arquiteto-only) e os CHECKs
-- tipo/storage_key/url NÃO são recriados (não têm allowlist de coluna). Material de `projeto_3d` carrega
-- ambiente_id (não-nulo); demais etapas seguem com ambiente_id nulo. CASCADE: ao excluir o cômodo, seus
-- anexos somem junto (o service apaga os bytes do storage ANTES; a cascata é rede de segurança).
alter table public.projeto_etapa_anexos
  add column if not exists ambiente_id uuid references public.projeto_ambientes(id) on delete cascade;
create index if not exists ix_projeto_etapa_anexos_ambiente
  on public.projeto_etapa_anexos (projeto_id, etapa, ambiente_id, ordem);

commit;
