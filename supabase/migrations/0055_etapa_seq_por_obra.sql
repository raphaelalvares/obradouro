-- 0055_etapa_seq_por_obra.sql
-- MUDANÇA DE REGRA: o seq_humano da ETAPA passa a ser POR OBRA (reseta a cada obra → #1, #2, #3...),
-- em vez de por tenant (que fazia a 1ª etapa de uma obra nova sair como #43). Itens/anexos continuam
-- por tenant (não exibem #). Inclui RENUMERAÇÃO das etapas já existentes (1..N por obra, na ordem de
-- exibição). seq_humano é rótulo de exibição (não documento fiscal) → renumerar é seguro.
-- Aplicar como postgres. DEV antes de PROD.

-- 1) Contador POR OBRA (espelha entity_seq_counters, mas escopado à obra). RLS ON, sem policy e sem
--    grant a cria_app → só o trigger SECURITY DEFINER (owner postgres) escreve.
create table if not exists public.obra_etapa_seq_counters (
  obra_id   uuid   not null references public.obras(id) on delete cascade,
  last_seq  bigint not null default 0,
  primary key (obra_id)
);
alter table public.obra_etapa_seq_counters enable row level security;

-- 2) Função que atribui o seq por obra (mesmo padrão concorrência-seguro do assign_entity_seq:
--    INSERT ... ON CONFLICT DO UPDATE trava a linha do contador até o commit).
create or replace function public.assign_etapa_seq()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_seq bigint;
begin
  if new.seq_humano is not null then
    return new;                                  -- idempotente: retry que já carrega o seq não renumera
  end if;
  insert into public.obra_etapa_seq_counters as c (obra_id, last_seq)
  values (new.obra_id, 1)
  on conflict (obra_id) do update set last_seq = c.last_seq + 1
  returning c.last_seq into v_seq;
  new.seq_humano := v_seq;
  return new;
end;
$$;
alter function public.assign_etapa_seq() owner to postgres;

-- 3) Troca o índice único de (tenant, seq) p/ (obra, seq). Dropar ANTES da renumeração (senão duas
--    obras com #1 colidiriam no índice antigo durante o UPDATE).
drop index if exists public.uq_etapas_tenant_seq;

-- 4) Renumera as etapas existentes: 1..N por obra, na ordem de exibição (ordem, created_at, id).
--    Bypassa o guard (no contexto da migration auth.uid() é nulo → is_arquiteto_ativo barraria o UPDATE).
alter table public.etapas disable trigger trg_etapas_guard;
with numbered as (
  select id, row_number() over (
           partition by obra_id order by ordem, created_at, id
         ) as rn
  from public.etapas
)
update public.etapas e
   set seq_humano = n.rn
  from numbered n
 where n.id = e.id
   and e.seq_humano is distinct from n.rn;
alter table public.etapas enable trigger trg_etapas_guard;

-- 5) Recria o índice único, agora por obra (defesa em profundidade do contador).
create unique index if not exists uq_etapas_obra_seq on public.etapas (obra_id, seq_humano);

-- 6) Inicializa o contador por obra com o maior seq atual de cada obra (para os próximos INSERTs
--    continuarem de onde parou).
insert into public.obra_etapa_seq_counters (obra_id, last_seq)
select obra_id, coalesce(max(seq_humano), 0)
  from public.etapas
 group by obra_id
on conflict (obra_id) do update set last_seq = excluded.last_seq;

-- 7) Troca o trigger da etapa: de assign_entity_seq('etapa') (por tenant) p/ assign_etapa_seq() (por
--    obra). Mantém o nome 'trg_etapas_seq' → continua disparando DEPOIS do 'trg_etapas_guard'.
drop trigger if exists trg_etapas_seq on public.etapas;
create trigger trg_etapas_seq
  before insert on public.etapas
  for each row execute function public.assign_etapa_seq();

-- Obs.: a linha 'etapa' em entity_seq_counters fica órfã (inofensiva); itens/anexos seguem usando-a.
