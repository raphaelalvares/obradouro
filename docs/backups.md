# Backups

> Erro mais comum de quem começa: deixar backup para depois. Aqui é **dia 1**.
> Os detalhes verificados (planos, PITR, comandos exatos) ficam em `docs/infra-notes.md`.

## O que precisa estar protegido

1. **Banco (Supabase/Postgres)** — dado estrutural do produto.
2. **VPS (EasyPanel/Hostinger)** — configuração, containers, variáveis.
3. **Mídia (Google Drive, a partir da Fase 4)** — fotos/documentos das obras.

## Estratégia inicial

- **Supabase:** habilitar os backups automáticos do plano (diários; PITR quando disponível no
  plano pago). Confirmar a janela de retenção do plano em `docs/infra-notes.md`.
- **Dump lógico de portabilidade:** rotina de `pg_dump` (ex.: semanal) guardada fora do
  Supabase. Serve de segunda cópia e casa com a portabilidade/LGPD (export). Automatizável depois.
- **VPS:** habilitar os snapshots da Hostinger/EasyPanel. Os segredos NÃO ficam só no
  container — estão documentados em cofre/secret manager para reprovisionar.
- **Mídia (Fase 4):** o módulo de storage define a política; o expurgo (offboarding) tem que ser
  real, então backups de mídia precisam de regra de retenção alinhada à LGPD.

## Teste de restauração

Backup não testado não é backup. Validar **uma restauração** de dump em dev logo na Fase 0
(critério de aceite da fase).
