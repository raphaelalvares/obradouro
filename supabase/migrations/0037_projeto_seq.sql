-- 0037_projeto_seq.sql  (Fase 5 — seq_humano por tenant para projeto/revisao/moodboard_item)
-- Reusa o contador GENÉRICO entity_seq_counters + assign_entity_seq() (0023). Estende o CHECK de
-- entity_type e liga os triggers '..._seq' (disparam DEPOIS de '..._guard' por ordem de nome).
-- ARMADILHA herdada: NUNCA ON CONFLICT nessas tabelas (queima seq) — a idempotência das RPCs
-- (criar_projeto/subir_revisao, 0041) checa existência + INSERT só de linha nova.

-- Estende o domínio. drop-if-exists + add => re-aplicável (DEV→PROD). LISTA COMPLETA (6 valores):
-- omitir 'anexo'/'etapa'/'checklist_item' quebraria a Fase 3/4 (o CHECK é um único constraint AND).
alter table public.entity_seq_counters
  drop constraint if exists entity_seq_counters_entity_type_check;   -- nome auto antigo
alter table public.entity_seq_counters
  drop constraint if exists entity_seq_counters_entity_type_chk;     -- nome explícito (0029 / re-run)
alter table public.entity_seq_counters
  add  constraint entity_seq_counters_entity_type_chk
  check (entity_type in ('etapa', 'checklist_item', 'anexo', 'projeto', 'revisao', 'moodboard_item'));

-- Triggers de seq (disparam DEPOIS do guard 0040: 'trg_<t>_guard' < 'trg_<t>_seq').
drop trigger if exists trg_projetos_seq on public.projetos;
create trigger trg_projetos_seq
  before insert on public.projetos
  for each row execute function public.assign_entity_seq('projeto');

drop trigger if exists trg_revisoes_seq on public.revisoes;
create trigger trg_revisoes_seq
  before insert on public.revisoes
  for each row execute function public.assign_entity_seq('revisao');

drop trigger if exists trg_moodboard_itens_seq on public.moodboard_itens;
create trigger trg_moodboard_itens_seq
  before insert on public.moodboard_itens
  for each row execute function public.assign_entity_seq('moodboard_item');
