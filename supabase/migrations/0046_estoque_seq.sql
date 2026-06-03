-- 0046_estoque_seq.sql  (Fase 6 — seq_humano por tenant para a NOTA FISCAL)
-- Reusa o contador GENERICO entity_seq_counters + assign_entity_seq() (0023). Só a NOTA tem rotulo
-- humano ("Nota #N"); os itens sao identificados pela nota+linha (sem seq). Estende o CHECK de
-- entity_type e liga o trigger '..._seq' (dispara DEPOIS de '..._guard' do 0048, por ordem de nome).
-- ARMADILHA herdada: NUNCA ON CONFLICT em notas_fiscais (queima seq) — a RPC de import (0049) checa
-- existencia pela chave e so faz INSERT de linha NOVA.

-- Estende o dominio. drop-if-exists + add => re-aplicavel (DEV->PROD). LISTA COMPLETA (7 valores):
-- omitir um quebraria as fases anteriores (o CHECK e um unico constraint).
alter table public.entity_seq_counters
  drop constraint if exists entity_seq_counters_entity_type_check;   -- nome auto antigo
alter table public.entity_seq_counters
  drop constraint if exists entity_seq_counters_entity_type_chk;     -- nome explicito (re-run)
alter table public.entity_seq_counters
  add  constraint entity_seq_counters_entity_type_chk
  check (entity_type in ('etapa', 'checklist_item', 'anexo', 'projeto', 'revisao',
                         'moodboard_item', 'nota_fiscal'));

drop trigger if exists trg_notas_fiscais_seq on public.notas_fiscais;
create trigger trg_notas_fiscais_seq
  before insert on public.notas_fiscais
  for each row execute function public.assign_entity_seq('nota_fiscal');
