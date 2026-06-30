-- 0097_projeto_pipeline.sql  (Portal do Cliente — LINHA DO TEMPO do projeto: 9 etapas fixas)
--
-- O projeto não tinha noção de etapa/status (o funil mora em oportunidades, CRM interno). Esta
-- migration cria a ESPINHA que o cliente acompanha no portal: 9 etapas FIXAS por projeto, cada uma com
-- um status. Os GATES de decisão NÃO são reimplementados — a etapa só "aponta" pro que já existe:
--   * layouts / aprovacao → Revisões (revisoes);
--   * orcamento (EVF)     → Proposta (orcamento_versoes / decidir_orcamento_versao, 0088);
--   * iniciar_obra        → decisão sim/não do cliente (decidir_iniciar_obra, abaixo) → o arquiteto
--                           roda virar_obra (que já leva o cliente p/ a obra — 0089).
-- "Espinha + gates atuais" (decisão do usuário): artefatos ricos (1-de-3 layouts, 3D por ambiente,
-- manual estruturado, Canva autofill) ficam p/ a 2ª rodada.
--
-- Depende de: 0034/0036 (projetos/RLS), 0089/0096 (cliente/expiry — o select reusa current_projeto_ids
-- já expiry-aware). Aplicar como postgres, após 0096. DEV antes de PROD. Sem backfill (semeadura
-- preguiçosa: garantir_etapas_projeto roda na criação do projeto e no 1º read do arquiteto).
-- Lição citext ([[portal-cliente-acesso]]): nada de citext sob search_path='' (não há e-mail aqui).

begin;

-- ===================== (1) enums =====================
do $$ begin
  if not exists (select 1 from pg_type where typname = 'etapa_projeto') then
    create type public.etapa_projeto as enum
      ('medicao', 'base', 'layouts', 'projeto_3d', 'apresentacao',
       'aprovacao', 'manual', 'orcamento', 'iniciar_obra');
  end if;
  if not exists (select 1 from pg_type where typname = 'status_etapa') then
    create type public.status_etapa as enum
      ('a_fazer', 'em_andamento', 'aguardando_cliente', 'concluida');
  end if;
end $$;

-- ===================== (2) tabela projeto_etapas (1 linha por projeto×etapa) =====================
create table if not exists public.projeto_etapas (
  id            uuid                 primary key default gen_random_uuid(),
  projeto_id    uuid                 not null references public.projetos(id) on delete cascade,
  tenant_id     uuid                 not null references public.profiles(id) on delete cascade,
  etapa         public.etapa_projeto not null,
  ordem         int                  not null,
  status        public.status_etapa  not null default 'a_fazer',
  data_prevista date,                                       -- agendamento (etapa medicao)
  concluida_em  timestamptz,
  decisao       text,                                       -- só iniciar_obra: 'sim' | 'nao'
  decidido_por  uuid                 references public.profiles(id) on delete set null,
  decidido_em   timestamptz,
  observacao    text,                                       -- nota/link (apresentacao Canva, manual…)
  created_at    timestamptz          not null default now(),
  updated_at    timestamptz          not null default now(),
  constraint uq_projeto_etapa unique (projeto_id, etapa),
  constraint projeto_etapas_decisao_chk check (decisao is null or decisao in ('sim', 'nao'))
);
create index if not exists ix_projeto_etapas_projeto on public.projeto_etapas (projeto_id);

drop trigger if exists trg_projeto_etapas_updated_at on public.projeto_etapas;
create trigger trg_projeto_etapas_updated_at
  before update on public.projeto_etapas for each row execute function public.set_updated_at();

-- ===================== (3) guard: identidade imutável =====================
-- Só status/data_prevista/concluida_em/decisao/decidido_*/observacao mudam. (decidir_iniciar_obra é
-- definer → passa por aqui também; muda só decisao/decidido_* → ok.) Espelha acessos_cliente_guard.
create or replace function public.projeto_etapas_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'UPDATE' then
    if new.id is distinct from old.id
       or new.projeto_id is distinct from old.projeto_id
       or new.tenant_id is distinct from old.tenant_id
       or new.etapa is distinct from old.etapa
       or new.ordem is distinct from old.ordem
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade da etapa e imutavel' using errcode = '42501';
    end if;
  end if;
  return new;
end;
$$;
alter function public.projeto_etapas_guard() owner to postgres;
drop trigger if exists trg_projeto_etapas_guard on public.projeto_etapas;
create trigger trg_projeto_etapas_guard
  before update on public.projeto_etapas for each row execute function public.projeto_etapas_guard();

-- ===================== (4) grants + RLS =====================
-- Cliente LÊ a timeline (current_projeto_ids já é expiry-aware — vencido não vê). Só o arquiteto
-- escreve via RLS; a decisão do cliente (iniciar_obra) é via a RPC definer.
grant select, insert, update, delete on public.projeto_etapas to cria_app;
alter table public.projeto_etapas enable row level security;

drop policy if exists projeto_etapas_select on public.projeto_etapas;
create policy projeto_etapas_select on public.projeto_etapas
  for select to authenticated
  using ( tenant_id = (select auth.uid())
          or projeto_id in (select public.current_projeto_ids()) );

drop policy if exists projeto_etapas_insert on public.projeto_etapas;
create policy projeto_etapas_insert on public.projeto_etapas
  for insert to authenticated
  with check ( tenant_id = (select auth.uid())
               and public.is_arquiteto_ativo_projeto(projeto_id) );

drop policy if exists projeto_etapas_update on public.projeto_etapas;
create policy projeto_etapas_update on public.projeto_etapas
  for update to authenticated
  using      ( public.is_arquiteto_ativo_projeto(projeto_id) )
  with check ( public.is_arquiteto_ativo_projeto(projeto_id) );

drop policy if exists projeto_etapas_delete on public.projeto_etapas;
create policy projeto_etapas_delete on public.projeto_etapas
  for delete to authenticated
  using ( public.is_arquiteto_ativo_projeto(projeto_id) );

-- ===================== (5) semeadura idempotente das 9 etapas =====================
create or replace function public.garantir_etapas_projeto(p_projeto uuid)
returns void language plpgsql security definer set search_path = '' as $$
declare v_tenant uuid;
begin
  -- qualquer MEMBRO ativo (não-vencido) semeia — assim o cliente também enxerga a timeline mesmo se
  -- o arquiteto nunca abriu o pipeline (projeto antigo, sem backfill). meu_papel_projeto é null p/
  -- não-membro/vencido → não semeia projeto alheio.
  if public.meu_papel_projeto(p_projeto) is null then
    return;
  end if;
  select tenant_id into v_tenant from public.projetos where id = p_projeto;
  if v_tenant is null then
    return;
  end if;
  insert into public.projeto_etapas (projeto_id, tenant_id, etapa, ordem)
  select p_projeto, v_tenant, e.etapa, e.ordem
  from (values
    ('medicao'::public.etapa_projeto, 1),
    ('base',         2),
    ('layouts',      3),
    ('projeto_3d',   4),
    ('apresentacao', 5),
    ('aprovacao',    6),
    ('manual',       7),
    ('orcamento',    8),
    ('iniciar_obra', 9)
  ) as e(etapa, ordem)
  on conflict (projeto_id, etapa) do nothing;
end;
$$;
alter function public.garantir_etapas_projeto(uuid) owner to postgres;
revoke all on function public.garantir_etapas_projeto(uuid) from public, anon;
grant execute on function public.garantir_etapas_projeto(uuid) to authenticated;

-- ===================== (6) estado dos GATES (definer: client lê mesmo sem RLS no orçamento) =====================
-- O cliente NÃO tem SELECT em orcamento_versoes (planilha do arquiteto) → não dá p/ derivar o gate de
-- orçamento sob a RLS dele. Esta função (definer, membro-only via meu_papel_projeto expiry-aware)
-- devolve o estado vivo dos gates p/ a timeline: revisão pendente, orçamento enviado-pendente,
-- orçamento já aprovado. NULL = não-membro/vencido (sem gates).
create or replace function public.pipeline_gates(p_projeto uuid)
returns jsonb language plpgsql stable security definer set search_path = '' as $$
declare
  v_rev       boolean;
  v_orc_pend  boolean;
  v_orc_aprov boolean;
begin
  if public.meu_papel_projeto(p_projeto) is null then
    return null;
  end if;
  v_rev := exists (
    select 1 from public.revisoes where projeto_id = p_projeto and status = 'pendente');
  v_orc_pend := exists (
    select 1 from public.orcamento_versoes
    where projeto_id = p_projeto and enviado and decisao is null and not congelado);
  v_orc_aprov := exists (
    select 1 from public.orcamento_versoes where projeto_id = p_projeto and decisao = 'aprovado');
  return jsonb_build_object(
    'rev_pendente', v_rev, 'orc_pendente', v_orc_pend, 'orc_aprovado', v_orc_aprov);
end;
$$;
alter function public.pipeline_gates(uuid) owner to postgres;
revoke all on function public.pipeline_gates(uuid) from public, anon;
grant execute on function public.pipeline_gates(uuid) to authenticated;

-- ===================== (7) decisão do cliente: iniciar a obra (sim/não) =====================
-- Gate final. Registra a decisão na etapa iniciar_obra; NÃO cria a obra (segue virar_obra do
-- arquiteto). meu_papel_projeto é expiry-aware (0096) → cliente vencido não decide. Espelha
-- decidir_orcamento_versao (0088).
create or replace function public.decidir_iniciar_obra(p_projeto uuid, p_decisao text)
returns void language plpgsql security definer set search_path = '' as $$
declare
  v_uid  uuid := (select auth.uid());
  v_nome text;
  v_seq  bigint;
begin
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;
  if p_decisao not in ('sim', 'nao') then
    raise exception 'decisao invalida' using errcode = '22023';
  end if;
  if public.meu_papel_projeto(p_projeto) is distinct from 'cliente' then
    raise exception 'apenas o cliente decide iniciar a obra' using errcode = '42501';
  end if;
  update public.projeto_etapas
    set decisao = p_decisao, decidido_por = v_uid, decidido_em = now()
  where projeto_id = p_projeto and etapa = 'iniciar_obra';
  if not found then
    raise exception 'etapa iniciar_obra inexistente' using errcode = 'P0002';
  end if;
  -- audit (evento de PROJETO; cliente é membro → cria_audit_log 11-arg aceita, igual à 0088)
  select pj.nome, pj.seq_humano into v_nome, v_seq from public.projetos pj where pj.id = p_projeto;
  perform public.cria_audit_log(
    null, null, null, 'projeto.iniciar_obra', 'projeto', p_projeto,
    jsonb_build_object('decisao', p_decisao), v_nome, v_seq, null, p_projeto);
end;
$$;
alter function public.decidir_iniciar_obra(uuid, text) owner to postgres;
revoke all on function public.decidir_iniciar_obra(uuid, text) from public, anon;
grant execute on function public.decidir_iniciar_obra(uuid, text) to authenticated;

commit;
