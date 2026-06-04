# Fase 9 — Cobrança (Stripe)

Última fase do roteiro. **Módulo SEPARADO** do controle de plano (planejamento §5: "não acoplar").
Quem decide "qual plano" continua em `tenant_assinaturas` (Fase 2); aqui ficam só os **fatos de
billing** do Stripe, e o webhook traduz o estado da assinatura → `plano_codigo`.

## Decisões

- **Caminho canônico SaaS:** Stripe **Checkout** (página hospedada → PCI leve) p/ assinar +
  **Customer Portal** (hospedado) p/ gerenciar/cancelar/trocar cartão + **webhooks** p/ refletir o
  estado. O **webhook é a fonte da verdade** do plano — nunca confiar no redirect de sucesso.
- **Degrada com graça:** chaves do Stripe são OPCIONAIS no settings. Sem
  `STRIPE_SECRET_KEY`/`STRIPE_PRICE_PRO` o app segue normal; checkout/portal/webhook respondem 503
  "não configurada" e a UI esconde os botões. `GET /me/cobranca` funciona sem Stripe (só lê o banco).
- **tenant_id por metadata:** setado no `client_reference_id` e em `subscription_data.metadata` ao
  criar o Checkout → o webhook resolve o tenant com segurança (não depende de mapear customer→tenant).
- **Webhook sem auth grava via SECURITY DEFINER:** o callback do Stripe não tem JWT/`auth.uid()`.
  As escritas vão por `cobranca_aplicar(...)` (owner postgres, grant a `cria_app`) — atualiza
  `tenant_cobranca` e espelha o plano em `tenant_assinaturas`. RLS continua barrando o acesso direto.
- **status → plano:** `active`/`trialing`/`past_due` → **pro** (past_due = período de graça);
  demais (canceled/unpaid/…) → **free**. Mapeamento em `mapear_evento` (PURO → testado).
- **Idempotente:** reprocessar o mesmo evento converge ao mesmo estado (upserts).
- **Cancelamento = downgrade (grandfathering)** — alinhado à Fase 2 (nada é arquivado; só a próxima
  ação que consome vaga bloqueia). O "perde acesso imediato + offboarding automático" (Fase 8) NÃO
  foi ligado aqui: precisa de Termos/jurídico (tarefa pré-lançamento §10). Fica como hook claro.

## Backend

- `config.py` — `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET`/`STRIPE_PRICE_PRO` (opcionais),
  `APP_BASE_URL` + props `cobranca_configurada` e `app_base_url` (redirects do Stripe).
- `0052_cobranca.sql` — `tenant_cobranca` (tenant_id PK, stripe_customer_id unique,
  stripe_subscription_id, status, current_period_end) + RLS self-select + funções SECURITY DEFINER
  `cobranca_set_customer` (checkout) e `cobranca_aplicar` (webhook). **GERADA — usuário APLICA.**
- `services/cobranca.py` — `status` (lê banco), `criar_checkout`, `criar_portal`, `mapear_evento`
  (puro), `processar_webhook` (verifica assinatura → mapeia → aplica via sessão própria sem RLS).
- `schemas/cobranca.py`, `routes/cobranca.py` — `GET /me/cobranca`, `POST /me/cobranca/checkout`,
  `POST /me/cobranca/portal`, `POST /cobranca/webhook` (raw body + assinatura). Registrados.
- `requirements.txt` — `stripe>=11,<13` (instalado: 12.5.1).
- Testes `tests/test_cobranca.py` (7: active→pro, past_due→pro, deleted/canceled→free, sem
  tenant→ignora, checkout.completed sem plano, evento irrelevante). **ruff limpo + 65 testes.**

## Front

- `features/conta/cobrancaApi.ts` — `useCobranca`, `useAssinar` (→ redireciona p/ Checkout),
  `usePortal` (→ Customer Portal), `useInvalidarCobranca`.
- `ConfiguracoesPage` → `PlanoCard`: plano + uso; botão **Assinar Pro** (free) ou **Gerenciar**
  (assinante); badge "pagamento pendente" (past_due); "renova/acesso até {data}"; trata o retorno
  `?cobranca=sucesso|cancelado` (toast + invalida + limpa a URL). **build front verde.**

## Setup pelo usuário (Stripe)
1. Criar produto **Pro** (preço recorrente) no Stripe → pegar o **Price ID** → `STRIPE_PRICE_PRO`.
2. `STRIPE_SECRET_KEY` (sk_...) no .env/EasyPanel.
3. Registrar o webhook `https://<api>/api/v1/cobranca/webhook` ouvindo
   `checkout.session.completed`, `customer.subscription.created/updated/deleted` → pegar o
   **signing secret** → `STRIPE_WEBHOOK_SECRET`.
4. `APP_BASE_URL` = origem do front (redirects do Checkout/Portal).
5. Aplicar `0052_cobranca.sql`.

## Pendências / futuro
- Aplicar `0052` + setar as chaves + commit/push.
- Ligar **cancelar → offboarding** (Fase 8: dispara export + revoga acesso) quando os Termos
  existirem.
- Provisionar o produto/preço via API (hoje manual) e tratar `invoice.payment_failed` (dunning).
