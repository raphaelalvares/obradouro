# supabase/

Migrations SQL do CRIA. **Geradas aqui, aplicadas por você no Supabase.**

- `migrations/` — arquivos `.sql` em ordem (`0000_...`, `0001_...`).
- Como aplicar e as convenções: ver [`../docs/migrations.md`](../docs/migrations.md).
- Specs de conexão / setup do CLI: ver `../docs/infra-notes.md`.

## Aplicar rapidamente (SQL Editor)

Supabase → projeto (dev primeiro) → **SQL Editor** → cole o `.sql` novo na ordem → **Run**.
Depois repita em prod.

## Estado atual

| Arquivo | Conteúdo |
|---|---|
| `migrations/0000_baseline.sql` | Extensões + `set_updated_at()` (Fase 0) |

As tabelas de identidade, tenancy e audit log entram na Fase 1.
