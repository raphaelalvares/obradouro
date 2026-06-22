-- 0085_valor_unitario_checklist.sql  (Custo calculado por metragem — preços UNITÁRIOS na tarefa)
--
-- Acrescenta os preços UNITÁRIOS em checklist_itens. O custo da obra é composição unitária (padrão de
-- orçamento de obra): material = quantidade × valor_unitario; mão de obra = quantidade × mao_obra_unitaria;
-- total = material + MO (sobrescrevível). custo_material/custo_mao_obra/custo_total (0043) guardam os
-- TOTAIS derivados; valor_unitario/mao_obra_unitaria guardam os preços por unidade. São só colunas novas
-- OPCIONAIS — NÃO recria guard: o checklist_itens_guard vivo (0083) trava coluna nova p/ prestador por
-- SUBTRAÇÃO (`to_jsonb(new) - estado - ...`), então as novas já ficam imutáveis p/ prestador e livres p/
-- arquiteto, sem mexer no guard. Grant é table-level (cobre as colunas novas). Aplicar como postgres.
-- DEV antes de PROD.

begin;

alter table public.checklist_itens
  add column if not exists valor_unitario    numeric(14,2),   -- R$/unidade do material (mat = qtd × este)
  add column if not exists mao_obra_unitaria numeric(14,2);   -- R$/unidade da MO  (MO  = qtd × este)

commit;
