# Fase 6 — Estoque (NF-e)

Entrada de materiais na obra a partir da **NF-e (XML)** + **conferência** (qtd da nota × qtd contada
em obra) + **saldo** por material. **Sem cunho fiscal**: o XML é lido só para extrair
produtos/qtds/valores. Independe de storage (o XML é guardado como texto na própria linha) — podia ser
paralelizada, conforme o roteiro.

## Modelo

- **`notas_fiscais`** (cabeçalho, escopo OBRA): `chave_acesso` (44 díg.), `numero/serie`,
  `emitente_nome/cnpj`, `data_emissao` (do XML), **`data_chegada`** (manual, ≠ emissão),
  `valor_total`, `xml` (cru, p/ auditoria/re-parse), `seq_humano` (rótulo "Nota #N").
- **`nota_itens`** (linhas de produto): `codigo (cProd)`, **`descricao (xProd) = nome fiel ao XML`**,
  **`nome_editado`** (correção opcional do arquiteto), `ncm`, `unidade`, `quantidade_nota (qCom)`,
  `valor_unitario (vUnCom)`, `valor_total (vProd)`, **`quantidade_conferida`** (NULL = não conferido)
  + `conferido_por/conferido_em`. `obra_id`/`tenant_id` **desnormalizados** (RLS sem JOIN).

## Decisões aplicadas

- **Dual-ID.** `id` UUID (gerado no backend ao parsear) + `seq_humano` por tenant **só na nota**
  (contador genérico do 0023, estendido p/ `'nota_fiscal'`); itens são identificados por nota+linha.
- **Idempotência = chave de acesso por tenant (ponto "g").** `uq_notas_tenant_chave` (parcial, onde
  chave não nula). Reimportar o MESMO XML devolve a nota existente (`criada=false`, `itens_novos=0`):
  **não duplica estoque**. A RPC NÃO usa `ON CONFLICT` na nota (queimaria seq via trigger): exists-check
  pela chave + a rara corrida cai no `EXCEPTION` (subtxn → rollback do INSERT e do seq). Advisory lock
  por chave serializa imports concorrentes.
- **Dados do XML são imutáveis; só `data_chegada` (nota) e `nome_editado` + conferência (item) variam.**
  Garantido pelos guards (verdade da nota preservada).
- **`data_chegada` ≠ `data_emissao`** — colunas separadas (a chegada é lançada à mão).
- **Conferência informacional.** `divergente` = `quantidade_conferida is not null and ≠ quantidade_nota`,
  calculado AO VIVO na leitura (sem coluna congelada). Saldo = `sum(coalesce(conferida, qtd_nota))`.

## Camadas de autorização (espelham o checklist/anexos)

1. **Service:** `obra_writable` (arquiteto: importar/editar nome/data_chegada/excluir nota) /
   `obra_executor` (arquiteto OU prestador: **conferir** — quem recebe em obra) / `obra_member` (lê).
2. **RLS:** select=membro; insert/delete/update da nota=arquiteto; update de item=`pode_executar_obra`
   (cliente negado já na RLS).
3. **Guards (regra fina):** `notas_fiscais_guard` (coerência tenant/obra; no UPDATE só `data_chegada`
   muda) e `nota_itens_guard` (campos do XML imutáveis p/ todos; arquiteto = `nome_editado`+conferência;
   prestador = **allowlist** só conferência; cliente = nada). Ordem dos triggers: `guard` → `seq`.

## Import (RPC `importar_nfe`, SECURITY DEFINER)

Backend faz o parse (`app/services/nfe_parser.py`, `xml.etree`, robusto a namespace via *local-name*;
aceita `<nfeProc>` ou `<NFe>`), gera UUIDs (nota + itens), monta o payload jsonb e chama a RPC, que
valida arquiteto ativo, dedupe pela chave e insere nota+itens numa txn. Audit `nota.importada`.

## Endpoints (`/api/v1/obras/{obra_id}/estoque`)

| Método | Rota | Quem | O quê |
|---|---|---|---|
| POST | `/importar` (multipart: `arquivo`) | arquiteto | parseia o XML e importa (idempotente) |
| GET | `/notas` | membro | lista (com totais: itens, conferidos, divergentes) |
| GET | `/notas/{id}` | membro | nota + itens |
| PATCH | `/notas/{id}` (`data_chegada`) | arquiteto | lança a data de chegada |
| DELETE | `/notas/{id}` | arquiteto | remove a nota (cascata nos itens) |
| PATCH | `/itens/{id}/nome` (`nome_editado`) | arquiteto | corrige o nome (mantém o fiel ao XML) |
| PATCH | `/itens/{id}/conferencia` (`quantidade_conferida`) | executor | confere a qtd recebida |
| GET | `/saldo` | membro | saldo agregado por material |

## Migrations (aplicar EM ORDEM)

`0045_estoque_tables` → `0046_estoque_seq` → `0047_estoque_access` → `0048_estoque_guards` →
`0049_estoque_import`. Reusam helpers existentes (`is_arquiteto_ativo`, `current_obra_ids`,
`pode_executar_obra`, `meu_papel_obra`, `cria_audit_log` 10-arg). Sem dependência de tabelas da Fase 5.

## Verificação

`prepare`/parse cobertos por **`tests/test_estoque.py`** (cabeçalho, itens, sem `nfeProc`, XML
inválido, sem `infNFe`, sem chave). ruff limpo + **46 testes**. Idempotência/divergência vivem no
banco (a verificar em integração após aplicar as migrations).

## Pendências / próximos passos

- **Front do módulo Estoque** (o card "Estoque" do hub da obra está "em breve"): importar XML, lista de
  notas com status de conferência, tela de conferência (qtd nota × contada, divergência destacada),
  saldo. **Próximo passo** (depois de aplicar 0045–0049 e validar o backend no schema real).
- **Saídas/consumo de estoque** (baixa por uso): fora do v1 (acceptance só pede import idempotente +
  divergência + datas). O modelo já isola entrada/conferência; um ledger de movimentos entra depois.
- **Lançamento manual** (sem XML): a coluna `chave_acesso` é nullable de propósito; endpoint manual
  pode entrar quando houver demanda.
