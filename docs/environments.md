# Ambientes e segredos

## Ambientes

| Ambiente | Backend | Supabase | Web |
|---|---|---|---|
| **development** | local (`uvicorn`) | projeto Supabase **dev** | local (Vite) |
| **production** | EasyPanel/Hostinger | projeto Supabase **prod** | Vercel |

> **Dois projetos Supabase separados** (dev e prod). Criar usuário admin / rodar migrations
> contra produção por engano é perigoso — por isso ambientes isolados desde o início.
> *(Opcional, no futuro: um `staging` espelhando prod.)*

## Variáveis de ambiente do backend

Definidas em `backend/.env` (local) e nas **Environment Variables do EasyPanel** (produção).
Template em `backend/.env.example`.

| Variável | O que é | Sensível? |
|---|---|---|
| `ENVIRONMENT` | `development` / `production` | não |
| `SUPABASE_URL` | URL do projeto (`https://<ref>.supabase.co`) | não |
| `SUPABASE_SERVICE_ROLE_KEY` | chave admin do Supabase (cria usuários, ignora RLS) | **SIM** |
| `SUPABASE_ANON_KEY` | chave pública (contextos de link/redirect) | não |
| `DATABASE_URL` | conexão Postgres (driver `asyncpg`) | **SIM** (tem senha) |
| `CORS_ORIGINS` | origens permitidas do web, separadas por vírgula | não |

> Os valores exatos de host/porta do `DATABASE_URL` (pooler Supavisor vs conexão direta)
> são confirmados em `docs/infra-notes.md`.

## Regras de segredos (importante)

- **Nunca** commitar `.env` (já no `.gitignore`). Só `backend/.env.example` (sem valores reais).
- A **service role key nunca** vai para os apps Flutter/React — só vive no backend
  (variável de ambiente do EasyPanel). Os apps falam com a API, nunca com o Supabase admin.
- A **service account do Google** (storage, Fase 4) é arquivo JSON sensível: fora do repo,
  injetada por variável/secret no EasyPanel. Padrões `service-account*.json` e `gcp-*.json`
  já estão no `.gitignore`.
- Em produção, preferir os **Secrets/Environment** do EasyPanel a arquivos no container.
