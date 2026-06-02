# CRIA — SaaS de Gestão de Obra para Arquitetos

Monorepo do CRIA: app (Flutter), painel web (React) e backend (Python/FastAPI),
sobre Supabase (Postgres + Auth) e Google Drive (mídia).

> **Estado:** Fase 0 (Fundação) em andamento. Veja o roteiro em
> [`docs/roadmap.md`](docs/roadmap.md).

## Estrutura do monorepo

```
/backend     API Python (FastAPI) — hospedada na VPS Hostinger via EasyPanel
/supabase    Migrations SQL (geradas aqui, aplicadas no Supabase)
/app         App Flutter (iOS + Android)            [entra na fase da sua feature]
/web         Painel web React (Vercel)              [entra na fase da sua feature]
/docs        Documentação de arquitetura e operação
```

> Decisão: começamos por **backend + migrations**. `/app` e `/web` são criados
> quando suas fases chegarem.

## Princípios de arquitetura (resumo)

- **API-only:** os apps falam **só** com a API Python; toda leitura/escrita passa pelo
  backend. RLS no Supabase é a **2ª camada** de segurança.
- **Identidade global:** uma conta por pessoa (`auth.users` + `profiles`); papel/tenant
  vivem em `obra_membros`. Sem CPF (minimização LGPD).
- **Offline é feature:** ids gerados no cliente (UUID) + `updated_at` em toda tabela
  editável; UI otimista.
- **Audit log é core**, não premium.

Detalhes e a ordem de construção completa em [`docs/roadmap.md`](docs/roadmap.md).

## Como rodar

- Backend: veja [`backend/README.md`](backend/README.md).
- Migrations: veja [`docs/migrations.md`](docs/migrations.md) e [`supabase/README.md`](supabase/README.md).
- Ambientes e segredos: [`docs/environments.md`](docs/environments.md).

## Documentação

- [`docs/roadmap.md`](docs/roadmap.md) — fases e decisões travadas
- [`docs/migrations.md`](docs/migrations.md) — como geramos/aplicamos migrations
- [`docs/environments.md`](docs/environments.md) — dev/prod, variáveis, segredos
- [`docs/api-versioning.md`](docs/api-versioning.md) — versionamento da API
- [`docs/backups.md`](docs/backups.md) — rotina de backup
- `docs/infra-notes.md` — specs verificadas de integração (gerado pela pesquisa de infra)
- `docs/briefing-juridico-lgpd.md` — briefing para a consultoria LGPD (gerado pela pesquisa)
