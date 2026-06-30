-- 0099_projeto_etapa_anexos.sql  (2ª rodada do portal — FEATURE B: material por etapa)
--
-- Cada etapa da linha do tempo (0097) pode ganhar MATERIAL que o cliente vê: um ARQUIVO (PDF do
-- Canva na apresentação, planta na base, imagem do 3D…) OU um LINK (tour 3D no Sketchfab, vídeo,
-- pasta). `anexos` (Fase 4) é OBRA-bound (parent_type etapa/checklist/diário…) → não serve p/ etapas
-- de PROJETO. Esta tabela espelha `revisao_arquivos` (projeto-scoped, imutável, bytes no
-- StorageBackend), com um discriminador `tipo` arquivo|link.
--
-- Só o arquiteto anexa/remove (guard + RLS); o cliente LÊ (current_projeto_ids já expiry-aware, 0096).
-- Depende de 0097 (projeto_etapas + enum etapa_projeto) e 0036/0089/0096 (RLS/cliente/expiry).
-- Aplicar como postgres, após 0098. DEV antes de PROD. Lição citext: nada de citext sob
-- search_path='' (não há e-mail aqui).

begin;

-- ===================== (1) tabela =====================
create table if not exists public.projeto_etapa_anexos (
  id            uuid                 primary key,                  -- gerado no cliente (dual-ID)
  projeto_id    uuid                 not null,
  tenant_id     uuid                 not null references public.profiles(id) on delete cascade,
  etapa         public.etapa_projeto not null,
  tipo          text                 not null check (tipo in ('arquivo', 'link')),
  label         text,                                              -- rótulo livre ("Planta baixa", "Tour 3D")
  url           text,                                              -- tipo='link'
  nome_arquivo  text,                                              -- tipo='arquivo'
  content_type  text,
  tamanho_bytes bigint               check (tamanho_bytes is null or tamanho_bytes >= 0),
  largura       int,
  altura        int,
  is_pdf        boolean              not null default false,
  storage_key   text,
  thumb_key     text,
  ordem         int                  not null default 0,
  criado_por    uuid                 references public.profiles(id) on delete set null,
  created_at    timestamptz          not null default now(),
  -- a etapa tem de ser uma linha REAL semeada do projeto (0097); cascata limpa junto com o projeto
  constraint fk_projeto_etapa_anexos_etapa
    foreign key (projeto_id, etapa) references public.projeto_etapas (projeto_id, etapa)
    on delete cascade,
  -- arquivo ⇔ tem storage_key; link ⇔ tem url (mutuamente exclusivos pelos dois checks)
  constraint projeto_etapa_anexos_arquivo_chk check ((tipo = 'arquivo') = (storage_key is not null)),
  constraint projeto_etapa_anexos_link_chk    check ((tipo = 'link')    = (url is not null))
);
create index if not exists ix_projeto_etapa_anexos_etapa
  on public.projeto_etapa_anexos (projeto_id, etapa, ordem, created_at);
create index if not exists ix_projeto_etapa_anexos_tenant
  on public.projeto_etapa_anexos (tenant_id);

-- ===================== (2) guard (imutável; só arquiteto — espelha revisao_arquivos_guard) =====================
create or replace function public.projeto_etapa_anexos_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.projetos pj
                   where pj.id = new.projeto_id and pj.tenant_id = new.tenant_id) then
      raise exception 'tenant/projeto incoerentes' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo_projeto(new.projeto_id) then
      raise exception 'apenas arquiteto anexa material da etapa' using errcode = '42501';
    end if;
    return new;
  end if;
  if tg_op = 'UPDATE' then
    raise exception 'anexo de etapa e imutavel' using errcode = '42501';
  end if;
  -- DELETE
  if not public.is_arquiteto_ativo_projeto(old.projeto_id) then
    raise exception 'apenas arquiteto remove material da etapa' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.projeto_etapa_anexos_guard() owner to postgres;
drop trigger if exists trg_projeto_etapa_anexos_guard on public.projeto_etapa_anexos;
create trigger trg_projeto_etapa_anexos_guard
  before insert or update or delete on public.projeto_etapa_anexos
  for each row execute function public.projeto_etapa_anexos_guard();

-- ===================== (3) grants + RLS =====================
-- Cliente LÊ (timeline do portal); só o arquiteto escreve. Sem UPDATE (imutável).
grant select, insert, delete on public.projeto_etapa_anexos to cria_app;
alter table public.projeto_etapa_anexos enable row level security;

drop policy if exists projeto_etapa_anexos_select on public.projeto_etapa_anexos;
create policy projeto_etapa_anexos_select on public.projeto_etapa_anexos
  for select to authenticated
  using ( tenant_id = (select auth.uid())
          or projeto_id in (select public.current_projeto_ids()) );

drop policy if exists projeto_etapa_anexos_insert on public.projeto_etapa_anexos;
create policy projeto_etapa_anexos_insert on public.projeto_etapa_anexos
  for insert to authenticated
  with check ( tenant_id = (select auth.uid())
               and public.is_arquiteto_ativo_projeto(projeto_id) );

drop policy if exists projeto_etapa_anexos_delete on public.projeto_etapa_anexos;
create policy projeto_etapa_anexos_delete on public.projeto_etapa_anexos
  for delete to authenticated
  using ( public.is_arquiteto_ativo_projeto(projeto_id) );

commit;
