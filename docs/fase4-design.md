# Fase 4 — Storage + Anexos

Mídia **informal** (foto/observação da execução) anexada a uma etapa ou a um item do checklist.
Entidade **independente** da revisão versionada do Módulo de Projeto (Fase 5): anexo não tem ciclo
de aprovação. Módulo mais arriscado do roteiro → storage isolado atrás de interface e testado.

## Decisões aplicadas

- **API-only.** O byte trafega `browser → API (multipart) → StorageBackend → API (stream) →
  browser`. Nenhum app fala com o storage direto. A imagem é servida pela API com `Authorization`
  (JWT), então o front busca por `fetch` autenticado e usa um **blob URL** (`<img src>` não envia o
  header). Sem URL pública e sem signed-URL no v1 — tudo sob RLS.
- **Storage atrás de módulo (trocável).** `app/services/storage/` define a interface
  `StorageBackend` (`guardar/recuperar/deletar/existe/tamanho/listar_chaves/deletar_prefixo`). O
  adapter de dev é **disco local** (`STORAGE_BACKEND=local`, sem credencial). Drive/S3/Supabase
  entram no `get_storage()` atrás da MESMA interface, **sem tocar no service de anexos**. Os 6 verbos
  do roteiro (guardar/recuperar/deletar/medir/empacotar/expurgar) mapeiam nos primitivos; empacotar
  (zip) é composto na Fase 8.
- **FK polimórfica (ponto "h" do review) resolvida desnormalizando `obra_id`.** O anexo aponta para
  `('etapa'|'checklist_item', parent_id)` **sem FK** (polimórfico), mas carrega `obra_id`/`tenant_id`
  próprios → RLS por `obra_id` sem JOIN + contabilização de consumo por tenant. Coerência (parent
  pertence à obra) e limpeza ao apagar o pai ficam em triggers (0031/0032).
- **Dual-ID.** `id` = UUID gerado no cliente (offline/idempotência); `seq_humano` por tenant
  (contador genérico do 0023, estendido p/ `'anexo'`).
- **Consumo = estado derivado.** Quota = `sum(tamanho_bytes)` por tenant (nunca um contador
  materializado), igual a obras_ativas. Eixo de plano `armazenamento_mb` (free 500 / pro ∞).
- **Quem anexa = quem executa** (arquiteto OU prestador; documentar a execução é trabalho do
  prestador). Cliente é read-only (vê a galeria). Prestador só apaga o **próprio** anexo.

## Camadas de autorização (espelham o checklist)

1. **Service (1ª camada):** `obra_executor` (arquiteto/prestador → 403 p/ cliente) / `obra_member`
   (qualquer membro lê) → 403/404 limpos cedo.
2. **RLS (2ª camada):** select=membro; insert/delete=`pode_executar_obra(obra_id)`; sem update
   (anexo é imutável).
3. **Guards no banco (regra fina):** `anexos_guard` valida coerência tenant/obra/parent, bloqueia
   update, e no delete refina prestador-só-o-próprio (`criado_por = auth.uid()`). `anexos_quota_guard`
   trava o INSERT por quota (P0001 parseável). Ordem dos triggers BEFORE INSERT por nome:
   `guard` (coerência/papel) → `quota` (não estoura → não queima seq) → `seq`.

## Pipeline de upload (idempotente + sem órfão)

1. `obra_executor` + idempotência (re-POST do mesmo `id` devolve o existente, sem re-upload/audit).
2. Valida parent na obra; lê bytes; rejeita vazio/`>MAX_UPLOAD_MB` (413); `process_image` (Pillow):
   orienta por EXIF, mede, reduz o `full` acima de `FULL_MAX_PX`, gera thumb JPEG. HEIC do iPhone →
   JPEG (via `pillow-heif`; sem o wheel, HEIC vira 415 e o resto segue).
3. **Grava a LINHA** (savepoint) → triggers de quota (P0001 → 403 + upsell) e seq.
4. **Grava os BYTES** (depois da linha validada). Falha → limpa parciais (`deletar_prefixo`) e o
   rollback da request desfaz a linha → **sem linha órfã**.
5. Audit `anexo.criado` (CORE, mesma txn).

**Reconciliação (`POST …/anexos/reconciliar`, só arquiteto):** chaves são namespeadas por anexo
(`<tenant>/<obra>/<anexo>/…`). Se o processo morrer entre 3 e 4, sobram **bytes sem linha** → a
varredura compara as chaves do prefixo da obra com os ids vivos no banco e expurga os órfãos.
Expurgo definitivo/retenção/`.zip` é a **Fase 8**; aqui o delete já remove os bytes (best-effort).

## Endpoints (`/api/v1/obras/{obra_id}`)

| Método | Rota | Quem | O quê |
|---|---|---|---|
| POST | `/anexos` (multipart: `id,parent_type,parent_id,arquivo`) | executor | sobe foto |
| GET | `/anexos?parent_type=&parent_id=` | membro | galeria do alvo |
| GET | `/anexos/{id}/conteudo?tipo=full\|thumb` | membro | bytes (blob no front) |
| DELETE | `/anexos/{id}` | executor (prestador só o próprio) | apaga linha + bytes |
| POST | `/anexos/reconciliar` | arquiteto | expurga bytes órfãos |

`GET /api/v1/me/quota` agora inclui `armazenamento: {usado_bytes, limite_mb}`.

## Front (fatia entregue)

Botão de **câmera** no cabeçalho da etapa e em cada item → `FotosDialog`: galeria (grid de thumbs),
upload (input `image/*` múltiplo, do celular), lightbox do `full`, excluir com confirmação. Quota
estourada → toast com o `detail` do problem+json. `AnexoImage` busca por fetch autenticado → blob
URL (cacheado no React Query, revogado no unmount).

## Config nova (`.env` do backend — defaults já funcionam em dev)

```
STORAGE_BACKEND=local      # adapter de bytes (local|...). Drive/S3 entram aqui depois.
STORAGE_DIR=.storage       # raiz do disco local (fora do git)
MAX_UPLOAD_MB=25           # acima → 413
THUMB_MAX_PX=512           # lado maior da miniatura
FULL_MAX_PX=2560           # acima disso o 'full' é reduzido
```

## Pendências / próximos passos

- **Produção:** disco local não sobrevive a redeploy sem volume; implementar o backend Drive/S3 (a
  interface já está pronta) antes de subir os anexos em prod.
- **Papel no front:** o painel é do arquiteto; o caso "cliente na web vê o botão e toma 403" é edge —
  expor o papel da obra ao front p/ esconder o upload do cliente fica como microfatia.
- **Reconciliação agendada / expurgo real + retenção 30d + `.zip`:** Fase 8.
- **Contagem de fotos inline no item:** evitado de propósito p/ não acoplar a árvore do checklist à
  tabela `anexos` (mantém o checklist funcionando mesmo antes de aplicar 0028+). Pode entrar depois.
