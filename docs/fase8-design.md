# Fase 8 — Ciclo de vida / offboarding (engine de export "em camadas")

Recorte do v1 (decidido com o usuário): a **engine de export / portabilidade LGPD** — independente
da cobrança e já útil. O **gatilho** "cancelou a conta → offboarding automático + perda de acesso"
fica para a **Fase 9** (cobrança), de onde o cancelamento nasce. Esta engine é a peça reusável que o
cancelamento vai acionar.

## Decisões

- **Job ASSÍNCRONO** (planejamento §9: "não segurar a tela"). v1 sem fila dedicada: FastAPI
  `BackgroundTasks` roda após a resposta, no mesmo processo — suficiente p/ o volume inicial; trocar
  por Celery/RQ depois não muda o contrato. O job vive no banco (`export_jobs`) → sobrevive como
  registro e é repolido pelo front.
- **Worker com contexto RLS próprio.** Background roda FORA do ciclo de request → abre a PRÓPRIA
  sessão (`SessionLocal` + `_set_rls_context(claims)`) com os claims do tenant → lê **só os dados
  dele** (a RLS continua valendo, sem exceção de owner). Sem service-role.
- **.zip "em camadas"** (planejamento §9): `leia-me.txt` + 1 pasta por obra com `checklist.csv`,
  `estoque.csv` e `fotos/`. CSV com separador `;` e BOM utf-8 → abre direto no Excel pt-BR. Dump
  bruto de SQL fica para depois (foto + CSV já cobre a portabilidade útil).
- **Montagem é função PURA** (`export_pacote`: `csv_checklist`/`csv_estoque`/`montar_zip`/`slug`) →
  testável sem DB/storage; o service só alimenta os dados já lidos.
- **Bytes no storage** (módulo da Fase 4), nunca no banco: `exports/{tenant}/{job}.zip`. O `export_jobs`
  guarda só a chave + status + tamanho + prazos.
- **Retenção 30 dias + expurgo REAL** (LGPD): `expira_em = pronto_em + 30d`. `expurgar_vencidos`
  apaga os bytes do storage de verdade (não só esconde) e marca `status='expirado'` (mantém o
  registro). Roda **lazy** no `listar`/`solicitar` do tenant. *(Cron global cross-tenant p/ expurgar
  sem o tenant logar = follow-up de prod, usa service-role.)*
- **Sem duplicar:** `solicitar` devolve o job em andamento se já houver um `pendente`/`processando`.
- **Self-only:** RLS `tenant_id = auth.uid()` em tudo; `baixar` exige dono + `pronto` + dentro do
  prazo (senão 404/409/410).

## Backend

- `0051_export_jobs.sql` — tabela `export_jobs` (id, tenant_id, status check, zip_key, tamanho_bytes,
  erro, pronto_em, expira_em) + índice + RLS self (4 policies). **GERADA — usuário APLICA.**
- `services/export_pacote.py` (puro) — CSV (`;`+BOM), `montar_zip`, `slug`.
- `services/export.py` — `solicitar`/`listar`/`get_job`/`baixar`/`expurgar_vencidos` (request) +
  `processar` (worker background, sessão+RLS próprios, 3 txns: processando → coleta+zip+storage →
  pronto; erro registrado no job).
- `schemas/export.py` — `ExportJobOut`. `routes/export.py` (prefixo `/me`): `POST/GET /me/exports`,
  `GET /me/exports/{id}`, `GET /me/exports/{id}/download` (zip). Registrado no router.
- Testes `tests/test_export.py` (4: slug, csv checklist/estoque BR, montar_zip estrutura+BOM).
  **ruff limpo + 58 testes + build front verde.**

## Front

- `features/conta/exportApi.ts` — `useExports` (refetch a cada 2,5s enquanto há job rodando),
  `useSolicitarExport`, `baixarExport` (blob → download).
- `ConfiguracoesPage` — card **"Exportar meus dados"**: botão Gerar (trava se há job rodando) + lista
  dos exports com status (Na fila/Gerando/Pronto/Falhou/Expirado), data, prazo e **Baixar** quando
  pronto.

## Pendências / futuro
- **Aplicar `0051`** no Supabase + commit/push.
- **Storage real (Drive/S3)** p/ o .zip sobreviver a redeploy e p/ o "expurgo real no Drive" da
  acceptance (hoje disco local; mesma pendência das Fases 4/7). Atrás da MESMA interface → pluga sem
  tocar no service.
- **Cron global de expurgo** (sem o tenant logar) — service-role/agendado.
- **Fase 9 (cobrança)**: ligar `cancelar conta → dispara export + revoga acesso imediato`
  (arquiteto+cliente+prestador) — o gatilho que faltou neste recorte. Também: e-mail com link quando
  o .zip fica pronto (hoje o front avisa por polling).
