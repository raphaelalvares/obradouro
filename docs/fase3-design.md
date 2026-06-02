# Fase 3 — Cronograma → Checklist (etapa → item) (as-built)

> 1ª fatia vertical de valor, **sem storage** (anexos são Fase 4). Backend-first. Desenho gerado por
> workflow multi-agente (3 lentes → síntese → 5 revisores adversariais) e **aterrado no repo real**;
> as correções dos achados (2 críticos, vários highs) estão refletidas abaixo. Migrations **0022–0026**.

## Modelo

- **`etapas`** (stage) → **`checklist_itens`** (item), pai/filho, escopados a uma **obra** (não projeto).
- **Dual-ID:** `id` UUID gerado no cliente (offline) + `seq_humano` por **tenant e por tipo** (rótulo
  humano, atribuído no servidor). `obra_id` e `tenant_id` **denormalizados** no item (RLS por `obra_id`
  sem JOIN; seq por-tenant sem JOIN). Coerência e imutabilidade do `tenant_id`/`obra_id`/`etapa_id`
  são garantidas pelos guards (0025).
- **3 estados fixos** (`public.estado_item` = `pendente | em_andamento | concluido`) — poka-yoke, sem
  texto livre. Transições são **any-to-any** (o "toggle" pode ir em qualquer direção; o ciclo natural
  é só convenção de UI, não imposto no banco).
- **`concluido_por` / `concluido_em`** no item: atribuição desnormalizada (mostrar "concluído por
  Fulano" na árvore sem varrer o audit), preenchidos/limpos no toggle junto com `estado`.
- **`nome_norm`**: chave natural de dedupe do import, materializada (não GENERATED). Computada SEMPRE
  pela MESMA função (`norm_nome`, backend) no create manual e no import. **Contrato congelado:**
  NFKD → remove diacríticos → `casefold` → colapsa espaços → "Fundação" = "fundacao" = "Fundaçao".

## Sequência (`entity_seq_counters`, 0023)

- Contador **genérico** `(tenant_id, entity_type, last_seq)` — serve etapa, item e entidades futuras
  (decisão travada: seq por-tenant **e** por-tipo). RLS on, **sem grant** a `cria_app` (só o trigger
  `SECURITY DEFINER` owner postgres escreve, por isenção de owner). `CHECK` pina os tipos válidos.
- **Armadilha resolvida (crítico):** `BEFORE INSERT + ON CONFLICT DO NOTHING` **queima** seq (o trigger
  roda antes da arbitragem do conflito; a linha é descartada mas o incremento persiste). Por isso
  **nenhum caminho usa `ON CONFLICT`** nestas tabelas: checa-se existência antes e só insere linha
  NOVA → o trigger só consome seq numa inserção real. Re-POST/re-import de linha existente = 0 queima.
- O trigger de seq (`trg_<tbl>_seq`) dispara **depois** do guard (`trg_<tbl>_guard`) — ordem alfabética
  de nome — então a coerência do `tenant_id` é validada antes de alocar seq.

## Autorização (3 camadas)

- **Camada 1 (serviço):** `obra_writable` (só arquiteto) nos verbos de edição estrutural; `obra_member`
  (qualquer membro ativo) na leitura e no toggle.
- **Camada 2a (RLS, 0024):** SELECT = qualquer membro ativo; **escrita já expressa o que dá**:
  etapas (insert/update/delete) e item (insert/delete) = `is_arquiteto_ativo`; item update =
  `pode_executar_obra` (arquiteto **ou** prestador) → cliente nem chega a escrever.
- **Camada 2b (guards, 0025):** regra **por-coluna** que a RLS não expressa. `prestador` é
  **allowlist**: só `estado`/`concluido_*` podem mudar (nome/ordem/seq/`created_at`/identidade
  travados). `cliente`/não-membro: nada. Se um guard cair, a RLS ainda barra cliente e barra
  prestador nos verbos estruturais.

| Papel | ver | criar/renomear/reordenar/excluir etapa & item | alternar estado do item | importar |
|---|---|---|---|---|
| arquiteto | ✅ | ✅ | ✅ | ✅ |
| prestador | ✅ | ❌ | ✅ | ❌ |
| cliente | ✅ | ❌ | ❌ | ❌ |

## Import idempotente (`importar_checklist`, 0026)

- Backend (`openpyxl`) lê o **template de colunas FIXAS** `etapa | item | ordem_etapa | ordem_item`
  (poka-yoke: "não é qualquer Excel"; cabeçalho validado exato → 422), normaliza, gera UUID por nó e
  chama a RPC com o payload jsonb. Parser **não descarta em silêncio**: item sem etapa anterior vira
  erro 422 com o nº da linha; dedupe dentro do arquivo (1ª ocorrência vence).
- RPC `SECURITY DEFINER`: valida arquiteto, deriva `tenant` da obra (não confia no caller), pega
  **advisory lock por obra** (serializa imports da mesma obra → fecha a corrida do `etapa_id` NULL),
  e para cada etapa/item: pré-checa por `nome_norm`; se nova, INSERT em subtransação (o raro conflito
  concorrente com create manual cai no `EXCEPTION`, revertendo o seq). Emite **`etapa.criada`/
  `item.criado` por linha nova** (audit é CORE). Reimportar o MESMO template = 0 novas, **não renumera
  nem reseta estado** de item já marcado.
- **Limite documentado:** a chave é o **nome atual**. Se o arquiteto renomear uma etapa/item no app e
  reimportar o template **original**, a linha volta a ser **criada** (chave não bate mais). Reimportar
  o template **inalterado** nunca duplica — esse é o critério de aceite. (Chave de import estável é
  evolução futura, se necessário.)

## Concorrência / offline

- **Create manual** = "garanta que existe": re-POST do MESMO uuid → devolve a linha sem re-auditar;
  colisão de **nome** (uuid diferente) → **MERGE** (devolve a linha existente; o cliente re-aponta seu
  objeto local) em vez de 409 — respeita a UX otimista offline.
- **Toggle de estado:** `SELECT … FOR UPDATE` trava a linha → captura o `de` real e evita lost-update
  concorrente; `estado_de` (base do cliente) é checado **antes** do no-op → conflito offline vira 409
  honesto. No-op idempotente (re-tap) não audita.
- **rename/reorder/delete** (só arquiteto) são **last-write-wins** assumido (sem token de versão);
  baixa contenção. Pode ganhar `expected_updated_at` depois se necessário.

## Audit (eventos, via `cria_audit_log` na mesma txn — identidade derivada de `auth.uid()`+obra)

`etapa.criada`/`etapa.renomeada`/`etapa.removida` (com `itens_removidos`), `item.criado`/
`item.renomeado`/`item.removido` (com `estado_final`), `item.estado_alterado` (`{de,para}`),
`checklist.importado` (resumo, `entity_type='obra'`). **Excluir uma etapa emite `item.removido` por
filho ANTES do cascade** (trilha reconstruível). Reorder não audita (proporcionalidade ao risco).

## API (prefixo `/api/v1/obras`)

- `GET /{obra_id}/checklist` → árvore (etapas + itens) numa tacada (serve a UX mobile).
- `POST /{obra_id}/etapas` · `PATCH /{obra_id}/etapas/{id}` · `PATCH …/etapas/{id}/ordem` · `DELETE …`
- `POST /{obra_id}/itens` · `PATCH /{obra_id}/itens/{id}` · `DELETE …`
- `PATCH /{obra_id}/itens/{id}/estado` → toggle (1 toque; `{estado, estado_de?}`).
- `POST /{obra_id}/checklist/importar` → multipart `.xlsx`.

## Verificação ao vivo (após aplicar 0022–0026 no dev)
1. Arquiteto cria etapa/item; reabrir a árvore mostra `seq_humano` e a estrutura.
2. Importar o template → conta novas; **reimportar o mesmo arquivo → 0 novas, sem duplicar**.
3. Prestador (membro ativo) faz `PATCH …/estado` (1 toque) e persiste; **cliente recebe 403**.
4. Prestador tentar renomear item → 403 (guard). RLS sozinho (backend desligado no teste): cliente
   não escreve; membro de outra obra não vê/edita.
5. Excluir etapa com N itens → no audit aparecem N `item.removido` + 1 `etapa.removida`.

## Aberto / próximo
- Template `.xlsx` para **download** (modelo em branco) — poka-yoke extra; quando o front existir.
- Chave de import estável (resistir a rename) — só se virar dor real.
- **Fase 4 — Storage + Anexos** (anexo com `obra_id` denormalizado, apontando p/ item OU etapa).
