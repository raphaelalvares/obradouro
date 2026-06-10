-- 0061_dependencias_cronograma.sql  (Fatia B — dependências de tarefas + cronograma automático)
-- Dependências FS (terminar→iniciar) entre TAREFAS top-level (parent_item_id IS NULL) da MESMA obra.
-- Habilita: (a) status "bloqueada" (poka-yoke: não inicia/conclui antes do predecessor — checado no
-- serviço/UI); (b) recálculo automático de datas pela cadeia (forward pass no serviço); (c) setas no
-- Gantt. + coluna duracao_dias na tarefa (comprimento desejado da barra, opcional, p/ o recálculo).
-- Aplicar como postgres (SQL Editor / db push). DEV antes de PROD.

-- ---------------------------------------------------------------------------------------------------
-- (1) Duração opcional na tarefa: comprimento da barra usado pelo recálculo; NULL = usa o span atual
--     (data_fim-data_inicio) ou 1 dia. Não altera nada da derivação existente (datas seguem o truth).
alter table public.checklist_itens
  add column if not exists duracao_dias int;

-- ---------------------------------------------------------------------------------------------------
-- (2) Recria o guard do item. IMPORTANTE: a base correta é o 0044 (allowlist REAL via to_jsonb), NÃO
--     o 0056 (que regrediu p/ denylist e deixou orçamento/parent_item_id escaparem p/ o prestador). A
--     allowlist `to_jsonb(new) - estado - conclusão` cobre duracao_dias (e qualquer coluna nova)
--     AUTOMATICAMENTE — por isso não há lista explícita de datas/duração. Mantém também a validação de
--     pai top-level no INSERT e a imutabilidade de parent_item_id (anti-reparent), ambas do 0044.
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

    v_papel := public.meu_papel_obra(old.obra_id);
    if v_papel = 'arquiteto' then
      return new;
    elsif v_papel = 'prestador' then
      -- ALLOWLIST real: só estado/conclusão (e updated_at do trigger) podem variar; o resto é imutável
      -- p/ o prestador — inclusive datas, duracao_dias, orçamento e parent_item_id (cobertos por subtração).
      if (to_jsonb(new) - 'estado' - 'concluido_por' - 'concluido_em' - 'updated_at')
         is distinct from
         (to_jsonb(old) - 'estado' - 'concluido_por' - 'concluido_em' - 'updated_at') then
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

-- ---------------------------------------------------------------------------------------------------
-- (3) Tabela de dependências (arestas). SEM seq_humano (não é entidade numerada pelo humano).
--     id gerado no cliente (offline). on delete cascade nas duas pontas → apagar tarefa some a aresta.
create table if not exists public.tarefa_dependencias (
  id              uuid        primary key,
  obra_id         uuid        not null references public.obras(id)            on delete cascade,
  tenant_id       uuid        not null references public.profiles(id)         on delete restrict,
  predecessora_id uuid        not null references public.checklist_itens(id)  on delete cascade,
  sucessora_id    uuid        not null references public.checklist_itens(id)  on delete cascade,
  tipo            text        not null default 'FS' check (tipo in ('FS','SS','FF','SF')),
  lag_dias        int         not null default 0 check (lag_dias >= 0 and lag_dias <= 3650),
  created_by      uuid        references public.profiles(id) on delete set null,
  created_at      timestamptz not null default now(),
  constraint tarefa_dep_nao_auto check (predecessora_id <> sucessora_id),
  constraint uq_tarefa_dep unique (sucessora_id, predecessora_id)  -- 1 aresta por par (direção fixa)
);
create index if not exists ix_tarefa_dep_sucessora    on public.tarefa_dependencias (sucessora_id);
create index if not exists ix_tarefa_dep_predecessora on public.tarefa_dependencias (predecessora_id);
create index if not exists ix_tarefa_dep_obra         on public.tarefa_dependencias (obra_id);

-- ---------------------------------------------------------------------------------------------------
-- (4) Guard: coerência tenant/obra, ambas as pontas = tarefas TOP-LEVEL da MESMA obra, só arquiteto
--     escreve, e ANTI-CICLO (se a sucessora JÁ alcança a predecessora, a aresta fecharia um ciclo).
--     Owner postgres; SECURITY DEFINER p/ ler obras/checklist_itens/dependências sob RLS.
create or replace function public.tarefa_dependencias_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    if not exists (select 1 from public.checklist_itens i
                   where i.id = new.predecessora_id and i.obra_id = new.obra_id
                     and i.parent_item_id is null) then
      raise exception 'predecessora deve ser tarefa top-level da obra' using errcode = '23514';
    end if;
    if not exists (select 1 from public.checklist_itens i
                   where i.id = new.sucessora_id and i.obra_id = new.obra_id
                     and i.parent_item_id is null) then
      raise exception 'sucessora deve ser tarefa top-level da obra' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo(new.obra_id) then
      raise exception 'apenas arquiteto pode criar dependencia' using errcode = '42501';
    end if;
    -- anti-ciclo: a aresta nova ainda NÃO existe (BEFORE INSERT) → percorre só as arestas atuais.
    if exists (
      with recursive reach as (
        select d.sucessora_id as n
          from public.tarefa_dependencias d
          where d.predecessora_id = new.sucessora_id
        union
        select d.sucessora_id
          from public.tarefa_dependencias d
          join reach r on d.predecessora_id = r.n
      )
      select 1 from reach where n = new.predecessora_id
    ) then
      raise exception 'dependencia criaria um ciclo' using errcode = '23514';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    -- identidade/escopo imutáveis; só tipo/lag_dias podem mudar (arquiteto).
    if new.id is distinct from old.id
       or new.obra_id is distinct from old.obra_id
       or new.tenant_id is distinct from old.tenant_id
       or new.predecessora_id is distinct from old.predecessora_id
       or new.sucessora_id is distinct from old.sucessora_id
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade da dependencia e imutavel' using errcode = '42501';
    end if;
    if not public.is_arquiteto_ativo(old.obra_id) then
      raise exception 'apenas arquiteto pode alterar dependencia' using errcode = '42501';
    end if;
    return new;
  end if;

  -- DELETE
  if not public.is_arquiteto_ativo(old.obra_id) then
    raise exception 'apenas arquiteto pode remover dependencia' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.tarefa_dependencias_guard() owner to postgres;
drop trigger if exists trg_tarefa_dependencias_guard on public.tarefa_dependencias;
create trigger trg_tarefa_dependencias_guard
  before insert or update or delete on public.tarefa_dependencias
  for each row execute function public.tarefa_dependencias_guard();

-- ---------------------------------------------------------------------------------------------------
-- (5) Grants + RLS (espelha o checklist 0024): SELECT p/ qualquer membro ativo; escrita só arquiteto
--     (o guard backstopa a regra fina + anti-ciclo).
grant select, insert, update, delete on public.tarefa_dependencias to cria_app;
alter table public.tarefa_dependencias enable row level security;

drop policy if exists tarefa_dep_select on public.tarefa_dependencias;
create policy tarefa_dep_select on public.tarefa_dependencias
  for select to authenticated
  using ( obra_id in (select public.current_obra_ids()) );

drop policy if exists tarefa_dep_insert on public.tarefa_dependencias;
create policy tarefa_dep_insert on public.tarefa_dependencias
  for insert to authenticated
  with check ( public.is_arquiteto_ativo(obra_id) );

drop policy if exists tarefa_dep_update on public.tarefa_dependencias;
create policy tarefa_dep_update on public.tarefa_dependencias
  for update to authenticated
  using      ( public.is_arquiteto_ativo(obra_id) )
  with check ( public.is_arquiteto_ativo(obra_id) );

drop policy if exists tarefa_dep_delete on public.tarefa_dependencias;
create policy tarefa_dep_delete on public.tarefa_dependencias
  for delete to authenticated
  using ( public.is_arquiteto_ativo(obra_id) );
