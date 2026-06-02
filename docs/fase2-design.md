# Fase 2 — Planos / Limites / Parametrização (as-built)

> Documento aterrado no que foi **realmente construído** (o workflow de design alucinou um
> "as-built" inexistente; aproveitamos a engenharia, corrigimos a numeração e os fatos).
> Migrations da Fase 2: **`0020_planos.sql`** e **`0021_limite_obras_ativas.sql`** (o `0019` é
> o hardening da Fase 1).

## Decisões (2026-06-02)

- **Planos: Free + Pro.** Free = 1 obra ativa, revisões 3. Pro = ilimitado (`-1`). Config
  centralizada → adicionar "Intermediário" depois é só um `INSERT` em `planos` (sem migração).
- **Flags no catálogo:** `export_pdf`, `logo`, `chat`, `historico` (todas `false` no Free, `true`
  no Pro). As features chegam nas fases delas; aqui só reservamos a flag.
- **Downgrade = grandfathering suave:** nada é arquivado; obras existentes seguem editáveis; só a
  próxima ação que consome vaga (criar/reativar) bloqueia até voltar abaixo do teto.
- **Soft-limit = HTTP 403** `application/problem+json` (RFC 9457) com `upgrade_cta`.
- **Cobrança continua desacoplada** (Fase 9): `tenant_assinaturas` só diz qual plano; gravar nela
  nunca chama a checagem de vaga (o webhook de downgrade nunca falha).

## Modelo (SQL — `0020`)

- `planos(codigo PK, nome, limites jsonb, flags jsonb, ativo, ordem, …)` — catálogo.
- `tenant_assinaturas(tenant_id PK→profiles, plano_codigo→planos, …)` — 1 linha por arquiteto.
- RLS **default-deny** (sem policy, sem grant a `cria_app`); acesso só via funções
  `SECURITY DEFINER` (owner postgres): `plano_do_tenant`, `plano_limite`, `plano_flag`.
- **Pitfall:** `plano_limite` faz `coalesce(...,0)` → eixo ausente vira **0 (bloqueia)**; por isso
  o seed traz todas as chaves. "Ilimitado" = `-1` explícito.

## Enforcement race-safe (SQL — `0021`)

- `_checar_vaga_obra_ativa(tenant)`: `pg_advisory_xact_lock(ns, tenant)` (serializa só o mesmo
  tenant, transaction-scoped) → conta obras `status='ativa'` → `raise P0001
  'limite_obras_ativas:<lim>:<atual>'` se cheio. Correto em READ COMMITTED + 1-request-1-transação.
- `criar_obra` v2: checa a vaga **só quando o id é novo** (idempotência offline) antes de inserir.
- `reativar_obra(id)`: `FOR UPDATE` na obra, valida existência (P0002→404) e papel (42501→403),
  idempotente, aplica a mesma checagem (BORDA 1: reativar acima do teto bloqueia).

## Backend

- `app/core/problems.py`: `LimiteAtivasError` + `limite_from_exc` (parser do P0001) +
  `limite_ativas_handler` (problem+json 403). Registrado em `main.py`.
- `app/services/obras.py`: `create_obra` e `set_status` (reativar) envolvem a RPC e convertem o
  P0001 em `LimiteAtivasError`. **Reativar agora passa por `reativar_obra`** (antes era UPDATE
  direto que furava o limite). Arquivar continua UPDATE direto (libera vaga, nunca excede).
- `GET /api/v1/me/quota` (`services/planos.py`): estado 100% derivado p/ o front montar o CTA —
  `{plano, obras_ativas:{em_uso,limite}, pode_criar_obra, flags}`.

## Contrato do soft-limit (exemplo)

```
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json
{ "type":"https://cria.app/problems/limite-obras-ativas", "title":"Limite de obras ativas atingido",
  "status":403, "detail":"Seu plano permite 1 obra(s) ativa(s); você já tem 1.",
  "eixo":"obras_ativas", "limite":1, "atual":1, "upgrade_cta":true }
```

## Verificação ao vivo (quando aplicar 0020/0021 no dev)
1. Free (sem assinatura → fallback): criar a 2ª obra ativa → **403 problem+json** (não 500).
2. Arquivar 1 + criar/reativar outra → ok; reativar a 1ª (voltaria a 2 ativas) → **403**.
3. `GET /me/quota` → `pode_criar_obra=false` quando `em_uso>=limite`.
4. Inserir `tenant_assinaturas(tenant, 'pro')` → limite vira ilimitado; criar várias → ok.

## Aberto / próximo
- Revisões: `revisoes_projeto` já está na config (Free=3, Pro=-1); a **aplicação** do limite é na
  Fase 5 (Módulo de Projeto), reusando `plano_limite(tenant,'revisoes_projeto')`.
- Gate de flags (`plano_flag`) será usado quando as features premium chegarem (Fase 6/7).
- Numbers/tiers extras (Intermediário) e preços: quando a cobrança (Fase 9) entrar.
