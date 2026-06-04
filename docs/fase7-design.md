# Fase 7 — Premium atrás de flags (PDF do checklist + personalização/logo)

Escopo v1 (fonte: roteiro + planejamento §5): os dois entregáveis concretos atrás de flag de plano.
`chat`, `cronograma avançado` e `histórico` são *candidatas* (planejamento §12: "começar com obras
ativas + 1–2 flags como relatório/export") — ficam para fases próprias (chat é módulo realtime).

A infra de planos da Fase 2 já existia: `planos.flags` jsonb com `export_pdf`, `logo`, `chat`,
`historico` (seed do `0020`), funções `plano_flag(tenant, chave)` e `/me/quota` devolvendo `flags`.
Esta fase só **consome** essas flags — nenhum migration de planos.

## Decisões

- **PDF gerado no backend (API-only).** Lib **fpdf2** (pure-Python, fontes core, sem dep de sistema
  → roda igual no Windows do dev e no container Linux). Core font = latin-1, que cobre o português;
  `_lat1` normaliza aspas/travessões e troca o resto por `?` (nunca estoura). Checkbox em ASCII
  (`[ ] [~] [x]`) — latin-1-safe e legível em P&B.
- **Renderização é função PURA** (`pdf_render.render_checklist_pdf`): recebe os dados já carregados
  e devolve bytes → testável sem DB/IO. O service (`checklist_pdf.gerar_pdf`) faz autorização +
  gate + carga e delega a montagem.
- **Gate de export:** `plano_flag(<tenant da obra>, 'export_pdf')`. A flag é do **dono** da obra, não
  do exportador → reflete "esta obra é de uma conta Pro". **Qualquer membro** pode exportar (cliente
  quer imprimir também). Flag desligada → `FeatureBloqueadaError('export_pdf')` → **403
  application/problem+json** com `upgrade_cta:true` (o front já reconhece via `ApiError.isUpgrade`).
- **Marca por TENANT** (nível-conta, não obra): tabela `tenant_branding` (`0050`) com
  `nome_escritorio`, `logo_key`, `logo_mime`. 1 linha por arquiteto. Sem seq, sem audit (escopo do
  `cria_audit_log` é obra/projeto; marca é conta).
- **Logo no storage** (módulo da Fase 4): só a CHAVE opaca + mime na tabela. `process_logo`
  (imaging) normaliza qualquer imagem p/ **PNG** (preserva transparência, reduz a 600px) — o fpdf2
  embute PNG nativamente.
- **Gate de personalização:** mutações (definir nome / subir logo) atrás da flag `'logo'` →
  `FeatureBloqueadaError('logo')`. Ler e **remover** são livres (limpar pós-downgrade não pode ficar
  preso).
- **RLS:** self-service por `tenant_id = auth.uid()` (o arquiteto só vê/edita a própria marca). O PDF
  pode ser gerado por cliente/prestador (não-dono) → leitura cross-tenant via
  **`branding_do_tenant(p_tenant)` SECURITY DEFINER** (expõe só os 3 campos de marca).

## Backend

- `0050_branding.sql` — `tenant_branding` + grants + RLS (4 policies = auth.uid()) +
  `branding_do_tenant` SECURITY DEFINER. **GERADA — usuário APLICA no Supabase (dev→prod).**
- `core/problems.py` — `FeatureBloqueadaError(eixo, detail)` + handler (403 problem+json,
  `eixo`, `upgrade_cta`). Registrado no `main.py`.
- `services/planos.py` — `tem_flag(session, eixo, tenant_id=None)` (corrente ou de outro tenant).
- `services/imaging.py` — `process_logo(raw, max_px=600) -> PNG bytes`.
- `services/branding.py` — get/update/upload/serve/delete (mutações gated por `'logo'`).
- `services/pdf_render.py` (puro) + `services/checklist_pdf.py` (orquestra).
- Rotas: `GET/PATCH /me/branding`, `PUT/GET/DELETE /me/branding/logo`,
  `GET /obras/{id}/checklist/pdf` (Content-Disposition attachment).
- `requirements.txt` — `fpdf2>=2.8,<3.0` (instalado no venv).
- Testes: `tests/test_pdf.py` (8: render produz %PDF, vazio, com/sem logo, logo inválido não quebra,
  `_lat1`, `_num`, `_agrupar`, `process_logo`→PNG). **ruff limpo + 54 testes.**

## Front

- `lib/api.ts` — `put`/`putForm` (PUT multipart do logo).
- `features/conta/contaApi.ts` — `useQuota`, `useBranding`, `useSalvarBranding`, `useUploadLogo`,
  `useRemoverLogo`; `LOGO_PATH`.
- `features/conta/ConfiguracoesPage.tsx` — card de plano (uso de obras/armazenamento) + card de
  personalização (nome + upload/preview/remover logo via `AnexoImage`). Free → card travado com
  cadeado e copy de upsell (`pode_personalizar=false`).
- `AppShell` — ícone de engrenagem (header) → `/configuracoes`. `App.tsx` — rota.
- `CronogramaPage` — botão **Exportar PDF** (impressora) só p/ arquiteto e com etapas; baixa o blob;
  403 `isUpgrade` → toast de upsell. **build verde.**

## Pendências / futuro
- **Aplicar `0050` no Supabase** + commit/push (deploy) p/ valer no ar.
- Logo em prod depende do storage Drive/S3 (mesma pendência da Fase 4 — disco local não sobrevive a
  redeploy sem volume).
- Cobrança real (mudar de plano) = Fase 9; hoje o upsell é informativo.
- Flags `chat`/`historico`/cronograma avançado = fases próprias.
