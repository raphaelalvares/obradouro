# CRIA — Backend (FastAPI)

API Python do CRIA. **API-only:** os apps Flutter/React falam só com esta API; o RLS do
Supabase é a 2ª camada de segurança.

## Requisitos

- Python 3.12+
- Um projeto Supabase (dev) — ver [`../docs/environments.md`](../docs/environments.md)

## Rodar localmente

```bash
cd backend
python -m venv .venv
# Windows:  .venv\Scripts\activate    |  Linux/Mac:  source .venv/bin/activate
pip install -r requirements-dev.txt

copy .env.example .env        # Windows  (Linux/Mac: cp .env.example .env)
# preencha .env com os valores do seu projeto Supabase

uvicorn app.main:app --reload
```

- App: http://localhost:8000
- Health: http://localhost:8000/api/v1/health
- Health do banco: http://localhost:8000/api/v1/health/db
- Docs (Swagger): http://localhost:8000/docs

## Testes e lint

```bash
pytest        # smoke tests (não precisam de banco)
ruff check .  # lint
ruff format . # formatação
```

## Estrutura

```
app/
  main.py              FastAPI app, CORS, monta a v1
  core/
    config.py          Settings (lê .env / env vars)
    database.py        engine async (SQLAlchemy + asyncpg) → Postgres do Supabase
    supabase.py        client admin (service role) — usado na Fase 1
  api/
    v1/
      router.py        agrega os routers da v1
      routes/
        health.py      /api/v1/health  e  /api/v1/health/db
tests/                 smoke tests
Dockerfile             imagem de produção (EasyPanel)
requirements.txt       deps de runtime (fonte de verdade p/ Docker)
requirements-dev.txt   deps de dev (lint/test)
```

## Deploy

Imagem Docker via `Dockerfile`, publicada no EasyPanel. **Contexto de build = raiz do repo**
(monorepo), então o build local roda da raiz:

```bash
docker build -f backend/Dockerfile -t cria-api .
```

No EasyPanel: Build = Dockerfile, File = `backend/Dockerfile`, Proxy Port = 8000. As variáveis
de ambiente (incluindo a service/secret key) entram nos **Secrets/Environment** do EasyPanel —
nunca no repo. Passo a passo completo (conexão, SSL, health) em
[`../docs/infra-notes.md`](../docs/infra-notes.md).

## Convenções

- Versionamento da API: [`../docs/api-versioning.md`](../docs/api-versioning.md)
- Migrations (schema): [`../docs/migrations.md`](../docs/migrations.md) — geradas em
  `../supabase/migrations`, aplicadas por você no Supabase.
