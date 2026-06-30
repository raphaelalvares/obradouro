-- 0101_projeto_manual.sql  (leva 2 do portal — MANUAL DO PROPRIETÁRIO estruturado, por CÔMODO)
--
-- A etapa `manual` (0097) deixa de ser só um slot de arquivo/link genérico (0099) e vira um MANUAL DO
-- IMÓVEL estruturado: o arquiteto cadastra, POR CÔMODO, os itens com marca/modelo/cor/fornecedor/
-- garantia/observações + anexos (nota fiscal, PDF de garantia/manual, foto, link); o CLIENTE consulta
-- no portal (read-only). NÃO há ciclo de aprovação (≠ 3D): o manual é informacional.
--
-- Reusa os CÔMODOS do projeto (`projeto_ambientes`, 0100) — os mesmos do 3D são a lista canônica.
-- Item sem cômodo (`ambiente_id` null) = balde "Geral". O material por item mora em
-- `projeto_etapa_anexos` (0099) + a coluna nova `manual_item_id` — reusa todo o pipeline de mídia
-- (imutável, bytes no StorageBackend), sem tabela nova. Depende de 0097 (etapa_projeto/projeto_etapas),
-- 0099 (projeto_etapa_anexos), 0100 (projeto_ambientes) e 0036/0096 (is_arquiteto_ativo_projeto /
-- current_projeto_ids, já expiry-aware).
-- Aplicar como postgres, após 0100. DEV antes de PROD. Lição citext: nada de citext sob search_path=''
-- (não há e-mail aqui).

begin;

-- ===================== (1) tabela de itens do manual (por cômodo; sem estado) =====================
create table if not exists public.projeto_manual_itens (
  id           uuid        primary key,                              -- gerado no cliente (dual-ID)
  projeto_id   uuid        not null references public.projetos(id)  on delete cascade,
  tenant_id    uuid        not null references public.profiles(id)  on delete restrict,
  ambiente_id  uuid        references public.projeto_ambientes(id)  on delete cascade,  -- null = "Geral"
  categoria    text,                              -- livre (Piso, Louças/Metais, Iluminação…)
  titulo       text        not null,              -- descrição do item ("Porcelanato da sala")
  marca        text,
  modelo       text,
  cor          text,                              -- cor / acabamento
  fornecedor   text,
  garantia     text,                              -- prazo + condições (texto livre)
  observacoes  text,                              -- manutenção / cuidados
  ordem        int         not null default 0,
  created_by   uuid        references public.profiles(id) on delete set null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index if not exists ix_projeto_manual_itens_grupo
  on public.projeto_manual_itens (projeto_id, ambiente_id, ordem, created_at);
drop trigger if exists trg_projeto_manual_itens_updated_at on public.projeto_manual_itens;
create trigger trg_projeto_manual_itens_updated_at
  before update on public.projeto_manual_itens for each row execute function public.set_updated_at();

-- ===================== (2) guard (arquiteto-only; cliente só LÊ — espelha o ramo arquiteto do 0100) =====================
create or replace function public.projeto_manual_itens_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.projetos pj
                   where pj.id = new.projeto_id and pj.tenant_id = new.tenant_id) then
      raise exception 'tenant/projeto incoerentes' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo_projeto(new.projeto_id) then
      raise exception 'apenas arquiteto cria item do manual' using errcode = '42501';
    end if;
    -- cômodo (se houver) tem de ser do MESMO projeto (fecha cross-room / cross-tenant)
    if new.ambiente_id is not null
       and not exists (select 1 from public.projeto_ambientes pa
                       where pa.id = new.ambiente_id and pa.projeto_id = new.projeto_id) then
      raise exception 'comodo de outro projeto' using errcode = '23514';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    -- identidade imutável p/ todos (inclui created_by — autoria não se reescreve; espelha 0100)
    if new.id is distinct from old.id
       or new.projeto_id is distinct from old.projeto_id
       or new.tenant_id is distinct from old.tenant_id
       or new.created_by is distinct from old.created_by
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade do item e imutavel' using errcode = '42501';
    end if;
    if not public.is_arquiteto_ativo_projeto(old.projeto_id) then
      raise exception 'apenas arquiteto edita o manual' using errcode = '42501';
    end if;
    if new.ambiente_id is distinct from old.ambiente_id
       and new.ambiente_id is not null
       and not exists (select 1 from public.projeto_ambientes pa
                       where pa.id = new.ambiente_id and pa.projeto_id = new.projeto_id) then
      raise exception 'comodo de outro projeto' using errcode = '23514';
    end if;
    return new;
  end if;

  -- DELETE
  if not public.is_arquiteto_ativo_projeto(old.projeto_id) then
    raise exception 'apenas arquiteto remove item do manual' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.projeto_manual_itens_guard() owner to postgres;
drop trigger if exists trg_projeto_manual_itens_guard on public.projeto_manual_itens;
create trigger trg_projeto_manual_itens_guard
  before insert or update or delete on public.projeto_manual_itens
  for each row execute function public.projeto_manual_itens_guard();

-- ===================== (3) grants + RLS (espelha projeto_etapas / 0097) =====================
-- Cliente LÊ (manual do portal) e só o arquiteto escreve. O guard refina papel/coluna em cada write.
grant select, insert, update, delete on public.projeto_manual_itens to cria_app;
alter table public.projeto_manual_itens enable row level security;

drop policy if exists projeto_manual_itens_select on public.projeto_manual_itens;
create policy projeto_manual_itens_select on public.projeto_manual_itens
  for select to authenticated
  using ( tenant_id = (select auth.uid())
          or projeto_id in (select public.current_projeto_ids()) );

drop policy if exists projeto_manual_itens_insert on public.projeto_manual_itens;
create policy projeto_manual_itens_insert on public.projeto_manual_itens
  for insert to authenticated
  with check ( tenant_id = (select auth.uid())
               and public.is_arquiteto_ativo_projeto(projeto_id) );

drop policy if exists projeto_manual_itens_update on public.projeto_manual_itens;
create policy projeto_manual_itens_update on public.projeto_manual_itens
  for update to authenticated
  using      ( public.is_arquiteto_ativo_projeto(projeto_id) )
  with check ( public.is_arquiteto_ativo_projeto(projeto_id) );

drop policy if exists projeto_manual_itens_delete on public.projeto_manual_itens;
create policy projeto_manual_itens_delete on public.projeto_manual_itens
  for delete to authenticated
  using ( public.is_arquiteto_ativo_projeto(projeto_id) );

-- ===================== (4) material do manual por item: manual_item_id em projeto_etapa_anexos =====================
-- ADD COLUMN puro: o projeto_etapa_anexos_guard (0099, imutável-no-update, arquiteto-only) e os CHECKs
-- tipo/storage_key/url NÃO são recriados (não têm allowlist de coluna). Material de `manual` carrega
-- manual_item_id (não-nulo) e ambiente_id nulo; 3D carrega ambiente_id; demais etapas seguem com os
-- dois nulos. CASCADE: ao excluir o item, seus anexos somem junto (o service apaga os bytes ANTES).
alter table public.projeto_etapa_anexos
  add column if not exists manual_item_id uuid
    references public.projeto_manual_itens(id) on delete cascade;
create index if not exists ix_projeto_etapa_anexos_manual
  on public.projeto_etapa_anexos (projeto_id, etapa, manual_item_id, ordem);

-- um anexo nunca é de 3D (ambiente_id) E de manual (manual_item_id) ao mesmo tempo (defesa em
-- profundidade — o service sempre seta no máximo um). ADD CONSTRAINT não tem IF NOT EXISTS → guard.
do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conname = 'projeto_etapa_anexos_alvo_chk'
      and conrelid = 'public.projeto_etapa_anexos'::regclass
  ) then
    alter table public.projeto_etapa_anexos
      add constraint projeto_etapa_anexos_alvo_chk
      check (ambiente_id is null or manual_item_id is null);
  end if;
end $$;

commit;
