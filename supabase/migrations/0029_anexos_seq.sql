-- 0029_anexos_seq.sql  (Fase 4 — seq_humano por tenant para anexos)
-- Reusa o contador GENERICO entity_seq_counters + assign_entity_seq() do 0023. Aqui so:
--   (1) estende o CHECK de entity_type para admitir 'anexo';
--   (2) liga o trigger de seq na tabela (nome '..._seq' dispara DEPOIS de '..._guard' do 0031).
-- Mesma armadilha do 0023: NUNCA usar ON CONFLICT em anexos (queimaria seq); o caminho idempotente
-- (re-POST do mesmo id) checa existencia ANTES e so faz INSERT de linha NOVA.

-- (1) estende o dominio de entity_type. drop-if-exists + add => re-aplicavel (DEV->PROD).
alter table public.entity_seq_counters
  drop constraint if exists entity_seq_counters_entity_type_check;   -- nome auto do inline check (0023)
alter table public.entity_seq_counters
  drop constraint if exists entity_seq_counters_entity_type_chk;     -- nome explicito (re-run desta migr.)
alter table public.entity_seq_counters
  add  constraint entity_seq_counters_entity_type_chk
  check (entity_type in ('etapa', 'checklist_item', 'anexo'));

-- (2) trigger de seq. Dispara DEPOIS do guard (validacao de coerencia/papel) por ordem de nome.
drop trigger if exists trg_anexos_seq on public.anexos;
create trigger trg_anexos_seq
  before insert on public.anexos
  for each row execute function public.assign_entity_seq('anexo');
