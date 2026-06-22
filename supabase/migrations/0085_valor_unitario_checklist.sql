-- 0085_valor_unitario_checklist.sql  (Custo calculado por metragem — valor unitário na tarefa)
--
-- Acrescenta `valor_unitario` em checklist_itens p/ o cálculo material = quantidade × valor_unitario
-- (total = MO + material). É só uma coluna nova OPCIONAL — NÃO recria guard: o checklist_itens_guard
-- vivo (0083) trava coluna nova p/ prestador por SUBTRAÇÃO (`to_jsonb(new) - estado - ...`), então
-- valor_unitario já fica imutável p/ prestador e livre p/ arquiteto, sem mexer no guard. Grant é
-- table-level (cobre a coluna nova). Aplicar como postgres. DEV antes de PROD.

begin;

alter table public.checklist_itens
  add column if not exists valor_unitario numeric(14,2);   -- R$/unidade (material = qtd × este)

commit;
