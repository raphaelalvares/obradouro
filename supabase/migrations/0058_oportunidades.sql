-- 0058_oportunidades.sql  (Comercial — micro-CRM: funil de oportunidades de venda)
-- OPORTUNIDADE: entidade TENANT-scoped (o funil é do arquiteto; cliente/prestador NÃO participam,
-- logo NÃO há tabela de membros — diferente de obras/projetos). UUID gerado no cliente (offline/
-- dual-ID) + seq_humano por tenant (contador genérico 0023/0037). Espelha projetos (0034/0039/0040):
-- guard de imutabilidade + coerência de tenant ao vincular obra; RLS dono-only (cinto-e-suspensório).
-- Etapa do funil = text + CHECK (poka-yoke; enxuta: lead→contato→visita→proposta + ganho/perdido).
-- "Ganho" pode VIRAR OBRA (oportunidades.obra_id; link 1:1 opcional, preenchido na conversão).

-- ===================== OPORTUNIDADES =====================
create table if not exists public.oportunidades (
  id               uuid        primary key,                                      -- gerado no cliente
  tenant_id        uuid        not null references public.profiles(id) on delete restrict,
  obra_id          uuid        references public.obras(id) on delete set null,   -- vínculo na conversão (1:1)
  nome             text        not null,                                         -- título da oportunidade
  etapa            text        not null default 'lead'
                     check (etapa in ('lead', 'contato', 'visita', 'proposta', 'ganho', 'perdido')),
  contato_nome     text,
  contato_telefone text,                                                         -- WhatsApp/telefone (livre)
  contato_email    text,
  origem           text,                                                         -- como chegou (indicação, etc.)
  valor_estimado   numeric(14, 2) check (valor_estimado is null or valor_estimado >= 0),
  proximo_followup date,                                                         -- próximo contato (lembrete)
  observacoes      text,
  seq_humano       bigint,                                                       -- trigger (abaixo)
  created_by       uuid        not null references public.profiles(id) on delete restrict,  -- histórico
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

create unique index if not exists uq_oportunidades_tenant_seq on public.oportunidades (tenant_id, seq_humano);
-- 1 obra origina-se de no MÁXIMO 1 oportunidade (parcial: NULL é o caso comum até converter).
create unique index if not exists uq_oportunidades_obra on public.oportunidades (obra_id) where obra_id is not null;
create index        if not exists ix_oportunidades_tenant_etapa on public.oportunidades (tenant_id, etapa);

drop trigger if exists trg_oportunidades_updated_at on public.oportunidades;
create trigger trg_oportunidades_updated_at
  before update on public.oportunidades
  for each row execute function public.set_updated_at();

-- ===================== seq_humano (estende o contador genérico 0023/0037/0046) =====================
-- LISTA COMPLETA (o CHECK é UM único constraint): partir da lista vigente do 0046 (que inclui
-- 'nota_fiscal') + 'oportunidade'. OMITIR qualquer valor quebraria a fase correspondente.
-- ('etapa' já é órfão desde 0055 — seq de etapa virou por-obra — mas fica na lista, inofensivo.)
alter table public.entity_seq_counters
  drop constraint if exists entity_seq_counters_entity_type_check;  -- nome auto antigo
alter table public.entity_seq_counters
  drop constraint if exists entity_seq_counters_entity_type_chk;    -- nome explícito (re-run)
alter table public.entity_seq_counters
  add  constraint entity_seq_counters_entity_type_chk
  check (entity_type in ('etapa', 'checklist_item', 'anexo', 'projeto', 'revisao',
                         'moodboard_item', 'nota_fiscal', 'oportunidade'));

-- ===================== GUARD (camada 2 — imutabilidade + coerência de tenant) =====================
-- Espelha projetos_guard (0040), porém SEM is_arquiteto_ativo (não há membros): dono = tenant_id.
-- A RLS já restringe a escrita ao dono; o guard fecha a imutabilidade da identidade e o vínculo de obra.
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
  return new;
end;
$$;
alter function public.oportunidades_guard() owner to postgres;
drop trigger if exists trg_oportunidades_guard on public.oportunidades;
create trigger trg_oportunidades_guard
  before insert or update on public.oportunidades
  for each row execute function public.oportunidades_guard();

-- seq DEPOIS do guard ('trg_..._guard' < 'trg_..._seq' na ordem de nome dos triggers BEFORE)
drop trigger if exists trg_oportunidades_seq on public.oportunidades;
create trigger trg_oportunidades_seq
  before insert on public.oportunidades
  for each row execute function public.assign_entity_seq('oportunidade');

-- ===================== GRANTS + RLS (dono-only; cinto-e-suspensório) =====================
grant select, insert, update, delete on public.oportunidades to cria_app;

alter table public.oportunidades enable row level security;

drop policy if exists oportunidades_select on public.oportunidades;
create policy oportunidades_select on public.oportunidades
  for select to authenticated
  using ( tenant_id = (select auth.uid()) );
drop policy if exists oportunidades_insert on public.oportunidades;
create policy oportunidades_insert on public.oportunidades
  for insert to authenticated
  with check ( tenant_id = (select auth.uid()) );
drop policy if exists oportunidades_update on public.oportunidades;
create policy oportunidades_update on public.oportunidades
  for update to authenticated
  using      ( tenant_id = (select auth.uid()) )
  with check ( tenant_id = (select auth.uid()) );
drop policy if exists oportunidades_delete on public.oportunidades;
create policy oportunidades_delete on public.oportunidades
  for delete to authenticated
  using ( tenant_id = (select auth.uid()) );
