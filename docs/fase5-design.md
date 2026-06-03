# Fase 5 — Módulo de Projeto

**Projeto ≠ Obra** (decisão travada): entidades separadas e relacionadas. Projeto pode anteceder/
originar uma obra e **pode existir SEM obra**. Decidido com o usuário: **escopo = fase inteira**
(onboarding + moodboard + ciclo de revisões) e **projeto é espaço próprio** (membros e código
próprios, link opcional a uma obra). Desenhada por workflow (3 propostas → síntese → revisão
adversarial em 8 dimensões = 55 achados, 28 crítico/alto). As correções estão embutidas nas
migrations `0034–0042`.

## Entidades (migrations 0034–0035)

- **`projetos`** — `tenant_id` (arquiteto), `obra_id` nullable (link **1:1** opcional, `partial
  unique`), `nome`, `briefing jsonb` (onboarding), `seq_humano`, `created_by`.
- **`projeto_membros`** — espelha `obra_membros`: papel (`arquiteto`/`cliente`; **prestador barrado**
  pelo guard), estado `pendente`/`ativo`, `invited_by`. Vínculo próprio do projeto.
- **`projeto_codigos`** — espelha `obra_codigos`: 24h, revogável, 1 ativo por projeto, papel cliente.
- **`revisoes`** — `numero` (R0,R1…, alocado sob lock), `status`
  (`pendente`/`aprovado`/`alteracao_pedida`/`recusado`), `motivo`, `alem_do_incluido` (congelado,
  informacional), `decidido_por`/`decidido_em`, `seq_humano`. Índices: `uq (projeto,numero)`,
  **`uq parcial (projeto) where status='pendente'`** (≤1 pendente), `uq (tenant,seq)`.
- **`revisao_arquivos`** — mídia da revisão (PDF/imagem). **Imutável** (espelha `anexos`: sem update).
  `is_pdf`, `storage_key`/`thumb_key` (PDF → thumb NULL). `projeto_id`/`tenant_id` denormalizados.
- **`moodboard_secoes`** / **`moodboard_itens`** — referências visuais (imagem, reusa storage/imaging).
  Arquiteto cura; cliente vê.

## Acesso e autorização (mesma filosofia das fases anteriores)

1. **Service (camada 1):** `projeto_writable` (arquiteto ativo) / `projeto_member` (qualquer membro
   ativo) → 403/404 limpos. **NUNCA** reusar `obra_executor`/`obra_member` (admitem prestador).
2. **RLS (camada 2):** `current_projeto_ids()`/`is_arquiteto_ativo_projeto()` (definer, quebram
   recursão). `profiles_select` ganhou ramo de projeto (arquiteto e cliente veem o nome um do outro).
   Toda policy UPDATE traz USING **e** WITH CHECK.
3. **Guards no banco (camada 3):** prestador fora (membros/códigos); anti-escalada de papel (espelha
   0019); **anti cross-tenant ao vincular obra** (obra do mesmo tenant); lifecycle da revisão por
   papel (numero/sinalização imutáveis; arquiteto não decide; cliente só decide **uma** pendente, com
   transição válida).

## Ciclo de revisões (núcleo)

- **`subir_revisao` (RPC definer):** autoriza arquiteto **antes** de ler `max(numero)`/lock (não vaza
  número nem trava projeto alheio); `pg_advisory_xact_lock(hashtext('cria:revisao_numero'),
  hashtext(projeto::text))`; idempotente sem `ON CONFLICT` (não queima seq); re-checa o id dentro do
  lock; garante 1 pendente. `numero` = `coalesce(max,-1)+1` (R0=0).
- **Verbos do cliente:** `aprovar`/`recusar`/`pedir alteração` = UPDATE em `revisoes` (status + motivo
  + `decidido_*`), validado pelo guard. Service trava a linha (`for update`) — espelha o toggle do
  checklist.
- **Limite = parâmetro do ARQUITETO por projeto (NÃO é eixo de plano free/pro):** o número de
  alterações incluídas é da relação arquiteto↔cliente (contrato), não da assinatura. Campo
  `projetos.revisoes_incluidas` (int, o arquiteto define no onboarding; **`NULL` = não controla**).
  A chave `revisoes_projeto` do seed de planos (0020) fica **descontinuada/inerte** (não usar).
- **Contador INFORMACIONAL, nunca financeiro, nunca trava, calculado AO VIVO:** `alem_do_incluido(N)
  = (revisoes_incluidas is not null and N > revisoes_incluidas)` — R0 = entrega base (0 alterações);
  R1,R2… = alterações. Sem coluna congelada: se o arquiteto renegociar o nº, o sinal acompanha; o
  fato do momento fica gravado no **audit** (imutável). Visível ao arquiteto **e ao cliente**.
  `restantes = max(0, revisoes_incluidas - numero_atual)` quando definido.

## Storage, quota e audit (reuso + correções)

- **Storage:** revisão e moodboard reusam o `StorageBackend`/imaging da Fase 4. **PDF** valida magic
  bytes `%PDF-`, não passa pelo imaging, `content_type` forçado, sem thumb; `serve` com `tipo=thumb`
  e `thumb_key` NULL → 404 (não cai no full). `tamanho_bytes` = `len(full)` (imagem reduzida) ou
  `len(raw)` (PDF). Chaves namespeadas por projeto; `reconciliar` ramifica por sub-namespace
  (`/moodboard/` vs `/revisoes/`) — **não** clonar o índice fixo de anexos (apagaria tudo).
- **Quota UNIFICADA:** `consumo_armazenamento_bytes(tenant)` soma anexos + moodboard_itens +
  revisao_arquivos; **um** guard genérico (`enforce_quota_armazenamento`) nos 3 triggers, mesmo
  advisory lock — fecha a brecha de fragmentar o limite entre módulos.
- **Audit (CORE):** coluna `audit_log.projeto_id` + `cria_audit_log` de **11 args** (deriva tenant do
  projeto quando não há obra) + ramo `projeto_id in current_projeto_ids()` em `audit_select` — assim
  arquiteto **e cliente** veem o histórico (a "prova de escopo"); senão `GET /audit` voltaria vazio
  ao cliente.

## API (backend — próxima fatia)

`/api/v1/projetos`: CRUD + onboarding; `/projetos/{id}/membros` + `/vinculo` (convite e-mail +
código + aceite, espelha Fase 1); `/projetos/{id}/vincular-obra`; `/projetos/{id}/revisoes` (subir +
listar + `/contador`) e verbos `/revisoes/{rid}/aprovar|recusar|alteracao`; `/revisoes/{rid}/arquivos`;
`/projetos/{id}/moodboard` (seções + itens, upload); `/projetos/{id}/audit`. `GET /me/quota` já cobre
armazenamento (somando os 3 módulos após 0042).

## Front (próxima fatia)

Top-level **Projetos** (lista + onboarding/briefing), hub do projeto (Briefing · Moodboard ·
Revisões · Membros · Histórico), entrar por **código de projeto**; timeline de revisões com os verbos
do cliente em 1 toque + contador gentil; moodboard (galeria, reusa `AnexoImage`); membros (convite/
código, espelha o padrão da obra). PDF → ícone (não pedir thumb).

## Pendências / próximos

- Backend + front desta fase (migrations já geradas, a aplicar no dev).
- Produção: revisão/moodboard herdam o storage local de dev → Drive/S3 antes de subir em prod.
- `reconciliar` de projeto + retenção/expurgo real = Fase 8.
