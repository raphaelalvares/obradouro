# Migrations

**Fluxo decidido:** o assistente **gera** os arquivos `.sql` em `supabase/migrations/`;
**você aplica** no Supabase. Nada de schema é alterado por código de aplicação — o Postgres é
a fonte da verdade do schema, versionada por estes arquivos.

## Convenções

- **Nome:** `NNNN_descricao.sql` em ordem crescente (ex.: `0000_baseline.sql`,
  `0001_identidade.sql`). O prefixo numérico garante ordem de aplicação determinística.
  *(Se você adotar o Supabase CLI, ele usa prefixo de timestamp `YYYYMMDDHHMMSS_` — veja
  `docs/infra-notes.md`; podemos migrar para esse formato sem retrabalho.)*
- **Idempotência quando possível:** `create extension if not exists`, `create table if not
  exists`, `create or replace function`. Facilita reaplicar em dev.
- **RLS junto da tabela:** toda tabela com dado de tenant nasce com `enable row level
  security` e suas policies **no mesmo arquivo** que a cria. RLS é a 2ª camada (a 1ª é o backend).
- **`updated_at` em tabela editável:** criar a coluna e o trigger usando
  `public.set_updated_at()` (definido no baseline) — decisão de offline/sync.
- **Uma migration = uma mudança coesa.** Não editar migrations já aplicadas em produção; criar
  uma nova.

## Como aplicar (duas opções)

**A) SQL Editor (mais simples para começar):** abra o projeto no Supabase → SQL Editor → cole o
conteúdo do `.sql` novo → Run. Aplique sempre na ordem dos números, primeiro em **dev**, depois
em **prod**.

**B) Supabase CLI (recomendado quando estabilizar):**
```bash
supabase link --project-ref <ref-do-projeto>
supabase db push          # aplica as migrations pendentes
```
Detalhes e setup do CLI em `docs/infra-notes.md`.

## Dev vs Prod

Dois projetos Supabase separados (ver `docs/environments.md`). **Sempre** aplicar e validar em
dev antes de prod. Manter os dois na mesma sequência de migrations.

## Ordem atual

| Arquivo | O que faz | Fase |
|---|---|---|
| `0000_baseline.sql` | Extensões + `set_updated_at()` (utilitário compartilhado) | 0 |
| `0001_enums_profiles.sql` | enums (papel/estado/status) + `profiles` + trigger `handle_new_user` | 1 |
| `0002_obras.sql` | `obras` (+ índices, trigger updated_at) | 1 |
| `0003_obra_membros.sql` | `obra_membros` (+ índices que sustentam a RLS) | 1 |
| `0004_obra_seq_counters.sql` | contador de seq por tenant (RLS, sem policy) | 1 |
| `0005_obra_seq_trigger.sql` | `assign_obra_seq()` + trigger BEFORE INSERT | 1 |
| `0006_obra_codigos.sql` | `obra_codigos` (código de obra, 24h, revogável) | 1 |
| `0007_audit_log.sql` | `audit_log` (owner postgres) | 1 |
| `0008_app_role.sql` | role `cria_app` + grants | 1 |
| `0009_audit_immutability.sql` | append-only do audit + `cria_audit_log()` | 1 |
| `0010_rls_enable.sql` | ENABLE RLS (sem FORCE) nas tabelas multi-tenant | 1 |
| `0011_rls_functions.sql` | `current_obra_ids()` (quebra recursão) | 1 |
| `0012_rls_profiles.sql` | policies de `profiles` | 1 |
| `0013_rls_obras.sql` | policies de `obras` | 1 |
| `0014_rls_obra_membros.sql` | policies de `obra_membros` | 1 |
| `0015_rls_pendentes.sql` | `minhas_obras_pendentes()` (rótulo magro) | 1 |
| `0016_rls_obra_codigos.sql` | policies de `obra_codigos` | 1 |
| `0017_rls_audit.sql` | policy SELECT de `audit_log` | 1 |
| `0018_funcoes_negocio.sql` | `criar_obra()`, `resgatar_codigo_obra()` | 1 |
| `0019_hardening_fase1.sql` | hardening pós-revisão: audit deriva ator/tenant; `is_arquiteto_ativo` + trava de papel; `tenant_id` imutável | 1 |
| `0020_planos.sql` | catálogo `planos` (Free+Pro) + `tenant_assinaturas` + `plano_do_tenant/limite/flag` | 2 |
| `0021_limite_obras_ativas.sql` | `_checar_vaga_obra_ativa` (advisory lock) + `criar_obra` v2 + `reativar_obra` | 2 |

Desenho completo (e justificativas) em [`fase1-design.md`](fase1-design.md).

### Passo manual após aplicar a Fase 1
Defina a senha da role de aplicação e use-a no `DATABASE_URL` do backend (usuário do pooler
`cria_app.<project-ref>`):

```sql
alter role cria_app password '<SENHA_FORTE>';   -- guardar como secret no EasyPanel, não no git
```

### Dois ajustes feitos vs `fase1-design.md`
1. **Ordem:** a role `cria_app` é criada (0008) **antes** dos grants/revokes de `audit_log` (0009)
   — o design tinha a referência adiantada.
2. **`ENABLE` sem `FORCE`:** as funções `SECURITY DEFINER` (owner `postgres`) precisam ignorar a
   RLS por **isenção de owner**; `FORCE` quebraria isso a menos que o `postgres` tivesse
   `BYPASSRLS` (incerto no Supabase). Como o backend conecta como `cria_app` (não-owner), o
   `ENABLE` já garante a RLS como 2ª camada.
