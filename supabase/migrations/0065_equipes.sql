-- 0065_equipes.sql  (Fatia A · parte 2 — Equipes: biblioteca REUTILIZÁVEL no tenant)
-- BIBLIOTECA do ARQUITETO (nível-TENANT, não por obra): equipes/turmas reutilizáveis entre obras,
-- com COR (p/ ler o Gantt "quem faz o quê quando") e contato. Cada tarefa (checklist_item) aponta p/
-- uma equipe via `equipe_id` (FK ON DELETE SET NULL — apagar a equipe só desliga das tarefas, não as
-- apaga). Espelha o catálogo de serviços (0063): RLS self (tenant = auth.uid()), SEM seq e SEM audit
-- (ativo de conta, igual a tenant_branding 0050). Aplicar como postgres. DEV antes de PROD.

begin;

-- ---------------------------------------------------------------------------------------------------
-- (1) Tabela de equipes (registro por TENANT). id = UUID do cliente (dual-ID). nome_norm = chave de
--     dedupe por tenant (mesmo norm_nome do checklist/catálogo: NFKD+sem acento+casefold). cor = hex
--     #RRGGBB (CHECK no banco + validação no backend; poka-yoke p/ o Gantt ficar legível).
create table if not exists public.equipes (
  id          uuid        primary key,
  tenant_id   uuid        not null references public.profiles(id) on delete cascade,
  nome        text        not null,
  nome_norm   text        not null,
  cor         text        not null default '#D8A53A' check (cor ~ '^#[0-9A-Fa-f]{6}$'),
  contato     text,                                    -- telefone/whatsapp/responsável (informativo)
  ativo       boolean     not null default true,       -- arquivar sem perder o histórico de uso
  created_by  uuid        references public.profiles(id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create unique index if not exists uq_equipes_tenant_norm on public.equipes (tenant_id, nome_norm);
create index if not exists ix_equipes_tenant on public.equipes (tenant_id, ativo, nome);
drop trigger if exists trg_equipes_updated_at on public.equipes;
create trigger trg_equipes_updated_at
  before update on public.equipes for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------------------------------
-- (2) Guard (SECURITY DEFINER, owner postgres): cinto-e-suspensório da RLS. INSERT só p/ o próprio
--     tenant; identidade imutável no UPDATE. NÃO checa created_by (a coluna é `on delete set null` —
--     um SET NULL ao apagar o profile dispararia este guard; espelha 0062/0063).
create or replace function public.equipes_guard()
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
      raise exception 'identidade da equipe e imutavel' using errcode = '42501';
    end if;
    return new;
  end if;
  return old;  -- DELETE
end;
$$;
alter function public.equipes_guard() owner to postgres;
drop trigger if exists trg_equipes_guard on public.equipes;
create trigger trg_equipes_guard
  before insert or update or delete on public.equipes
  for each row execute function public.equipes_guard();

-- ---------------------------------------------------------------------------------------------------
-- (3) Grants + RLS self (espelha servicos_catalogo 0063 / tenant_branding 0050).
grant select, insert, update, delete on public.equipes to cria_app;
alter table public.equipes enable row level security;

drop policy if exists equipes_select on public.equipes;
create policy equipes_select on public.equipes
  for select to authenticated
  using ( tenant_id = (select auth.uid()) );

drop policy if exists equipes_insert on public.equipes;
create policy equipes_insert on public.equipes
  for insert to authenticated
  with check ( tenant_id = (select auth.uid()) );

drop policy if exists equipes_update on public.equipes;
create policy equipes_update on public.equipes
  for update to authenticated
  using      ( tenant_id = (select auth.uid()) )
  with check ( tenant_id = (select auth.uid()) );

drop policy if exists equipes_delete on public.equipes;
create policy equipes_delete on public.equipes
  for delete to authenticated
  using ( tenant_id = (select auth.uid()) );

-- ---------------------------------------------------------------------------------------------------
-- (4) Vínculo no item (set null ao apagar a equipe — a tarefa não some). A equipe é nível-TENANT;
--     a coerência cross-tenant (tarefa do tenant X não pode apontar p/ equipe do tenant Y) é checada
--     no guard recriado abaixo + no service (a RLS self da equipe já barra a leitura cross-tenant).
alter table public.checklist_itens
  add column if not exists equipe_id uuid references public.equipes(id) on delete set null;
create index if not exists ix_itens_equipe_id on public.checklist_itens (equipe_id);

-- ---------------------------------------------------------------------------------------------------
-- (5) RECRIA o guard do item. Base = 0061 (allowlist REAL via to_jsonb — que já cobre equipe_id p/ o
--     prestador AUTOMATICAMENTE: equipe_id não está na subtração, logo o prestador não pode alterá-la).
--     ÚNICA adição vs 0061: checagem CROSS-TENANT do equipe_id (a equipe referenciada tem de ser do
--     MESMO tenant do item) no INSERT e quando o equipe_id muda no UPDATE. Tudo o mais é idêntico ao
--     0061 (validação de pai top-level, imutabilidade de parent_item_id, papéis).
create or replace function public.checklist_itens_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    if not exists (select 1 from public.etapas e
                   where e.id = new.etapa_id and e.obra_id = new.obra_id) then
      raise exception 'etapa nao pertence a obra do item' using errcode = '23514';
    end if;
    -- sub-item: pai precisa existir, na mesma etapa/obra, e ser top-level (só 2 níveis de item).
    if new.parent_item_id is not null then
      if not exists (select 1 from public.checklist_itens pai
                     where pai.id = new.parent_item_id
                       and pai.etapa_id = new.etapa_id
                       and pai.obra_id = new.obra_id
                       and pai.parent_item_id is null) then
        raise exception 'sub-item: pai invalido (outra etapa/obra ou ja e sub-item)'
          using errcode = '23514';
      end if;
    end if;
    -- equipe é nível-tenant: só pode apontar p/ equipe do MESMO tenant do item (anti cross-tenant).
    if new.equipe_id is not null
       and not exists (select 1 from public.equipes eq
                       where eq.id = new.equipe_id and eq.tenant_id = new.tenant_id) then
      raise exception 'equipe de outro tenant' using errcode = '42501';
    end if;
    if not public.is_arquiteto_ativo(new.obra_id) then
      raise exception 'apenas arquiteto pode criar item' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    -- identidade/escopo (inclui o pai) nunca mudam por UPDATE (vale até p/ arquiteto)
    if new.id is distinct from old.id
       or new.tenant_id is distinct from old.tenant_id
       or new.obra_id  is distinct from old.obra_id
       or new.etapa_id is distinct from old.etapa_id
       or new.parent_item_id is distinct from old.parent_item_id
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade/escopo do item sao imutaveis' using errcode = '42501';
    end if;
    -- equipe nova (quando muda) tem de ser do mesmo tenant (vale p/ qualquer papel; o prestador nem
    -- chega a mudar equipe_id por causa da allowlist abaixo, mas a checagem é barata e defensiva).
    if new.equipe_id is not null and new.equipe_id is distinct from old.equipe_id
       and not exists (select 1 from public.equipes eq
                       where eq.id = new.equipe_id and eq.tenant_id = new.tenant_id) then
      raise exception 'equipe de outro tenant' using errcode = '42501';
    end if;

    v_papel := public.meu_papel_obra(old.obra_id);
    if v_papel = 'arquiteto' then
      return new;
    elsif v_papel = 'prestador' then
      -- ALLOWLIST real: só estado/conclusão (e updated_at do trigger) podem variar; o resto é imutável
      -- p/ o prestador — inclusive datas, duracao_dias, orçamento, equipe_id e parent_item_id (subtração).
      if (to_jsonb(new) - 'estado' - 'concluido_por' - 'concluido_em' - 'updated_at')
         is distinct from
         (to_jsonb(old) - 'estado' - 'concluido_por' - 'concluido_em' - 'updated_at')
      then
        raise exception 'prestador so pode alterar o estado do item' using errcode = '42501';
      end if;
      return new;
    else
      raise exception 'sem permissao para alterar item' using errcode = '42501';
    end if;
  end if;

  if not public.is_arquiteto_ativo(old.obra_id) then
    raise exception 'apenas arquiteto pode remover item' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.checklist_itens_guard() owner to postgres;
-- trigger trg_itens_guard (0025) já aponta p/ esta função; não recriar.

commit;
