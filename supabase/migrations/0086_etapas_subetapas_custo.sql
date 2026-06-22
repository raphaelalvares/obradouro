-- 0086_etapas_subetapas_custo.sql  (Custo em QUALQUER nível-folha: etapa/subetapa também)
--
-- O custo passa a poder morar em qualquer FOLHA da EAP — uma Etapa sem subetapa/tarefa, ou uma
-- Subetapa sem tarefa, pode carregar custo/MO/metragem direto (antes só `checklist_itens` tinha). O
-- invariante "custo na folha mais baixa" é mantido no service: ao ganhar o 1º filho, o nó vira
-- agregador e o custo é EMPURRADO pro 1º filho (o pai zera). O rollup soma só folhas (front/PDF), então
-- agregador zerado nunca dobra.
--
-- Só ADD COLUMN (idempotente). NÃO recria guard: etapas_guard (0025) e subetapas_guard (0080) são
-- arquiteto-only sem allowlist por-coluna → colunas novas entram livres p/ arquiteto e barradas p/
-- prestador (que nem faz UPDATE). Grants são table-level (0024/0080) → cobrem as colunas novas. A
-- máscara de LEITURA do prestador (zerar custo) é feita no service (get_tree). Mesmo bloco de custo do
-- checklist_itens (0043 + valor_unitario/mao_obra_unitaria do 0085): preços UNITÁRIOS (valor_unitario,
-- mao_obra_unitaria) + TOTAIS derivados (custo_material, custo_mao_obra, custo_total). Aplicar como
-- postgres, DEPOIS da 0085. DEV antes de PROD.

begin;

alter table public.etapas
  add column if not exists unidade           text,
  add column if not exists quantidade        numeric(14,3),
  add column if not exists valor_unitario    numeric(14,2),
  add column if not exists mao_obra_unitaria numeric(14,2),
  add column if not exists custo_mao_obra    numeric(14,2),
  add column if not exists custo_material    numeric(14,2),
  add column if not exists custo_total       numeric(14,2);

alter table public.subetapas
  add column if not exists unidade           text,
  add column if not exists quantidade        numeric(14,3),
  add column if not exists valor_unitario    numeric(14,2),
  add column if not exists mao_obra_unitaria numeric(14,2),
  add column if not exists custo_mao_obra    numeric(14,2),
  add column if not exists custo_material    numeric(14,2),
  add column if not exists custo_total       numeric(14,2);

commit;
