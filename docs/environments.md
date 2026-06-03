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
| `CORS_ORIGINS` | origens EXATAS permitidas do web (vírgula) | não |
| `CORS_ORIGIN_REGEX` | regex p/ origens dinâmicas (previews Vercel); opcional | não |
| `INVITE_REDIRECT_URL` | deep link / URL p/ onde o convite-senha redireciona; opcional | não |

> Os valores exatos de host/porta do `DATABASE_URL` (pooler Supavisor vs conexão direta)
> são confirmados em `docs/infra-notes.md`.

## Domínios / DNS (obradouro.com.br — Registro.br)

| Host | Aponta para | Registro DNS |
|---|---|---|
| `obradouro.com.br` (apex) | painel web (Vercel) | **A** → IP que a Vercel mostrar (ex.: `76.76.21.21`) |
| `www.obradouro.com.br` | painel web (Vercel) | **CNAME** → `cname.vercel-dns.com.` |
| `api.obradouro.com.br` | backend (EasyPanel/Hostinger) | **A** → IP do VPS |

> DNS editado no **modo avançado** (editor de zona) do Registro.br. SSL: Vercel emite automático
> no apex/www; no `api.` o EasyPanel emite via Let's Encrypt. Propagação: minutos a horas.

### Valores de produção (EasyPanel — backend)
```
ENVIRONMENT=production
CORS_ORIGINS=https://obradouro.com.br,https://www.obradouro.com.br
CORS_ORIGIN_REGEX=^https://obradouro-[a-z0-9-]+\.vercel\.app$   # opcional (previews)
```

### Valores de produção (Vercel — front)
```
VITE_API_BASE_URL=https://api.obradouro.com.br
VITE_SUPABASE_URL=https://<ref-prod>.supabase.co
VITE_SUPABASE_ANON_KEY=<anon-key-prod>
```

> Lembrar: **Supabase → Authentication → URL Configuration** deve listar `https://obradouro.com.br`
> (e `www`) em Site URL / Redirect URLs, senão o login pelo SDK quebra.

## Regras de segredos (importante)

- **Nunca** commitar `.env` (já no `.gitignore`). Só `backend/.env.example` (sem valores reais).
- A **service role key nunca** vai para os apps Flutter/React — só vive no backend
  (variável de ambiente do EasyPanel). Os apps falam com a API, nunca com o Supabase admin.
- A **service account do Google** (storage, Fase 4) é arquivo JSON sensível: fora do repo,
  injetada por variável/secret no EasyPanel. Padrões `service-account*.json` e `gcp-*.json`
  já estão no `.gitignore`.
- Em produção, preferir os **Secrets/Environment** do EasyPanel a arquivos no container.
