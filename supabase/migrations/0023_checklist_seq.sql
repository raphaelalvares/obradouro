-- 0023_checklist_seq.sql  (Fase 3 — contador de seq_humano por (tenant, tipo de entidade))
-- Decisao travada: seq por-tenant E por-tipo. Contador GENERICO (serve etapa, item e entidades
-- futuras). Espelha 0004/0005. Ninguem escreve direto: so o trigger SECURITY DEFINER (owner
-- postgres, por isencao de owner). RLS habilitada SEM policy e SEM grant a cria_app => negado.
--
-- ARMADILHA tratada (revisao adversarial): "BEFORE INSERT + ON CONFLICT DO NOTHING" QUEIMA seq
-- (o trigger roda antes da arbitragem do conflito; a linha e descartada mas o incremento persiste).
-- Por isso os caminhos idempotentes (create manual e import) NUNCA usam ON CONFLICT nestas tabelas:
-- checam existencia antes e so dao INSERT real de linha NOVA. Assim o trigger so consome seq quando
-- ha insercao de fato. Gaps por rollback continuam aceitaveis (seq e rotulo, nao documento fiscal).
create table if not exists public.entity_seq_counters (
  tenant_id   uuid   not null references public.profiles(id) on delete cascade,
  entity_type text   not null check (entity_type in ('etapa', 'checklist_item')),
  last_seq    bigint not null default 0,
  primary key (tenant_id, entity_type)
);
-- RLS ON, sem policy => cria_app negado. SEM grant a cria_app (igual obra_seq_counters no 0008):
-- so o trigger definer mexe. (Asserido por ausencia de grant; nao ha grant a revogar.)
alter table public.entity_seq_counters enable row level security;

-- Atribui seq_humano. tenant vem de NEW.tenant_id (que o guard 0025 ja validou == obras.tenant_id,
-- pois o guard dispara ANTES deste trigger: 'trg_<tbl>_guard' < 'trg_<tbl>_seq' na ordem alfabetica
-- de nomes em que o Postgres dispara triggers BEFORE de mesma tabela). tipo vem de tg_argv[0].
-- Idempotente: se seq_humano ja veio setado (ex.: retry que o carregue), NAO renumera.
create or replace function public.assign_entity_seq()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_seq  bigint;
  v_type text := tg_argv[0];                          -- 'etapa' | 'checklist_item'
begin
  if new.seq_humano is not null then
    return new;
  end if;

  insert into public.entity_seq_counters as c (tenant_id, entity_type, last_seq)
  values (new.tenant_id, v_type, 1)
  on conflict (tenant_id, entity_type) do update
    set last_seq = c.last_seq + 1                      -- lock de linha do (tenant,tipo) ate o commit
  returning c.last_seq into v_seq;

  new.seq_humano := v_seq;
  return new;
end;
$$;
alter function public.assign_entity_seq() owner to postgres;  -- escreve no contador via isencao de owner

-- Nome do trigger ('..._seq') ordena DEPOIS do guard ('..._guard') => o guard valida coerencia/
-- papel ANTES de o seq ser alocado (fecha "seq queimado para tenant forjado").
drop trigger if exists trg_etapas_seq on public.etapas;
create trigger trg_etapas_seq
  before insert on public.etapas
  for each row execute function public.assign_entity_seq('etapa');

drop trigger if exists trg_itens_seq on public.checklist_itens;
create trigger trg_itens_seq
  before insert on public.checklist_itens
  for each row execute function public.assign_entity_seq('checklist_item');
