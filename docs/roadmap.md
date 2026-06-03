# Roadmap de construção — CRIA

Cópia de trabalho do roteiro. Fonte canônica (com a revisão completa de contradições/lacunas):
`C:\Users\rapha\.claude\plans\leia-este-documento-de-optimized-newell.md`.
Documento de planejamento original do usuário: `planejamento-app-obra.md`.

## Decisões travadas (2026-06-02)

- **Acesso API-only.** Apps falam só com a API Python; RLS é 2ª camada; chat/realtime no
  Python (não Supabase Realtime direto no app).
- **Offline é feature confirmada.** Modelar para sync desde já: UUID gerado no cliente +
  `updated_at` em toda tabela editável; UI otimista com marca de "não sincronizado".
- **Identidade global.** Uma conta por pessoa (`auth.users` + `profiles`), PK = `auth.users.id`,
  unicidade por email, **sem CPF**. `created_by` é só histórico; tenant/papel só em `obra_membros`.
- **Produto tem 2 fases: PROJETO ≠ OBRA** (entidades separadas). Ciclo de revisões é
  **informacional, nunca financeiro**; cliente vê o contador de revisões.
- **Audit log é CORE** (não premium), 2 camadas: cru imutável + exibição legível (snapshot do
  rótulo + ID sequencial, nunca UUID).
- **ID dupla-face:** UUID interno (PK, gerado no cliente) + sequencial humano por tenant
  (atribuído pelo backend).
- **Stack:** FastAPI (backend) · Supabase/Postgres · React/Vercel (web) · Flutter (app) ·
  Google Drive (mídia) · EasyPanel/Hostinger (deploy). Monorepo.
- **Migrations:** geradas aqui (`/supabase/migrations`), aplicadas por você no Supabase.
- **Conexão DB:** Supavisor Session Pooler (porta 5432, IPv4). ⚠️ Conectar como `postgres`
  (owner) faz **bypass de RLS** — para a RLS valer como 2ª camada na API, a Fase 1 cria uma
  **role de aplicação dedicada** (não-owner) + contexto de usuário por request. Ver
  `docs/infra-notes.md`.

## Ordem de construção

- **Fase 0 — Fundação** *(em andamento)*: repos/monorepo, migrations, ambientes dev/prod,
  backups, segredos, versionamento da API.
- **Fase 1 — Espinha:** `auth.users` + `profiles`, `obras`, `obra_membros` (pendente/ativo),
  ID sequencial por tenant, **audit log core**, criação de usuário no backend + convite/código +
  deep link de senha, RLS de isolamento por obra **com role de aplicação dedicada** (a conexão
  como `postgres`/owner faz bypass de RLS — ver `docs/infra-notes.md`).
- **Fase 2 — Planos/limites + parametrização** (eixo "obras ativas"; limite de revisões na mesma config).
- **Fase 3 — Cronograma → Checklist** (1ª vertical; sem storage; import por template de Excel).
- **Fase 4 — Storage + Anexos** *(backend pronto; front: fotos no checklist)* — módulo isolado
  (interface trocável; adapter disco local no dev, Drive/S3 atrás depois); `obra_id` denormalizado;
  consumo derivado (eixo `armazenamento_mb`). Detalhe em `docs/fase4-design.md`.
- **Fase 5 — Módulo de Projeto** (onboarding + moodboard + ciclo de revisões).
- **Fase 6 — Estoque (NF-e)** (parser; conferência nota×contagem; idempotência por chave de acesso).
- **Fase 7 — Premium atrás de flags** (PDF do checklist, logo, etc.).
- **Fase 8 — Offboarding** (job assíncrono; `.zip` em camadas; retenção 30 dias; expurgo real no Drive).
- **Fase 9 — Cobrança (Stripe).**
- **Em paralelo desde já:** consultoria LGPD + Termos + Política de Privacidade
  (ver `docs/briefing-juridico-lgpd.md`).
