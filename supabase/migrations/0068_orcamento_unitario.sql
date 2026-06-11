-- 0068_orcamento_unitario.sql  (Orçamento: valor_mo/material/equipamento viram UNITÁRIO)
-- BUG recorrente: no diálogo de item, mudar a QUANTIDADE alterava os valores de M.O/Material, porque o
-- modelo guardava esses 3 campos como SUBTOTAL de linha (e a qtd escalava). O conceito correto é:
--   valor_mo/material/equipamento = custo UNITÁRIO; subtotal da linha = valor × quantidade.
-- (Nas planilhas importadas — ITEM|DESCRIÇÃO|UN|QTD|M.O|MAT|TOTAL — as colunas M.O/MAT são SUBTOTAL de
--  linha POR BALDE, com TOTAL = M.O+MAT+EQUIP; o import passa a dividir por qtd p/ obter o unitário.)
-- Alinha o orçamento ao CATÁLOGO (unitário). O backend passa a multiplicar por quantidade em TODO
-- lugar (totais/central/etapa/cômodo). Aplicar como postgres, DEPOIS da 0060. DEV antes de PROD.
--
-- ATENÇÃO: a conversão de dados (subtotal → unitário) é ÚNICA e NÃO reexecutável (dividir 2× erraria).
-- Migrations rodam uma vez, em ordem — não reaplique a 0068.

begin;

-- (0) PRÉ-CHECAGEM: nenhum unitário resultante pode estourar numeric(18,4) (~1e14). Aborta com
--     mensagem CLARA (em vez do 22003 críptico que faria rollback de tudo) se houver linha com
--     quantidade minúscula + valor enorme. Roda ANTES de qualquer DDL → nada muda se falhar.
do $$
declare n int;
begin
  select count(*) into n
  from public.orcamento_itens
  where greatest(
          case when quantidade > 0 then round(valor_mo / quantidade, 4)          else valor_mo end,
          case when quantidade > 0 then round(valor_material / quantidade, 4)     else valor_material end,
          case when quantidade > 0 then round(valor_equipamento / quantidade, 4) else valor_equipamento end
        ) > 99999999999999.9999;
  if n > 0 then
    raise exception
      '0068: % linha(s) de orcamento_itens com custo unitario acima do teto numeric(18,4) — '
      'corrija (quantidade muito pequena ou valor enorme) antes de aplicar', n;
  end if;
end $$;

-- (1) Precisão UNITÁRIA numeric(18,4): 4 casas decimais (como o catálogo) + faixa inteira AMPLA
--     (14 dígitos). NÃO usar numeric(14,4): cortaria a faixa de 12→10 dígitos e a re-validação do
--     ALTER (que roda ANTES da divisão) abortaria com qualquer subtotal já gravado ≥ 1e10. (18,4) é
--     widening do (14,2) → o ALTER nunca estoura, e a divisão por qtd<1 ainda cabe.
alter table public.orcamento_itens
  alter column valor_mo          type numeric(18,4),
  alter column valor_material    type numeric(18,4),
  alter column valor_equipamento type numeric(18,4);

-- (2) Converte os dados existentes: SUBTOTAL de linha → UNITÁRIO = subtotal / quantidade.
--     qtd null/0 = verba (a linha JÁ é o "unitário", multiplicador 1) → NÃO divide (espelha o _mult
--     do backend: mult = qtd>0 ? qtd : 1, que preserva o total dessas linhas).
--     O guard (orcamento_itens_guard) barraria este UPDATE: roda sem auth.uid() (→ não-arquiteto) e
--     toca versões CONGELADAS (só-leitura). Como postgres é dono da tabela, desliga o guard só aqui;
--     se algo falhar, o rollback da transação restaura o estado do trigger.
alter table public.orcamento_itens disable trigger trg_orcamento_itens_guard;
update public.orcamento_itens
   set valor_mo          = round(valor_mo / quantidade, 4),
       valor_material    = round(valor_material / quantidade, 4),
       valor_equipamento = round(valor_equipamento / quantidade, 4)
 where quantidade is not null and quantidade > 0;
alter table public.orcamento_itens enable trigger trg_orcamento_itens_guard;

-- (3) Documenta a nova semântica das colunas.
comment on column public.orcamento_itens.valor_mo
  is 'custo UNITÁRIO M.O (R$); subtotal da linha = valor × quantidade';
comment on column public.orcamento_itens.valor_material
  is 'custo UNITÁRIO material (R$); subtotal da linha = valor × quantidade';
comment on column public.orcamento_itens.valor_equipamento
  is 'custo UNITÁRIO equipamento (R$); subtotal da linha = valor × quantidade';

commit;
