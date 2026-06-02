-- 0000_baseline.sql
-- Fase 0 (Fundação): extensões e utilitários COMPARTILHADOS. Sem tabelas de feature.
--
-- Fluxo: este arquivo é gerado aqui e aplicado por você no Supabase
-- (SQL Editor ou `supabase db push`). Ver docs/migrations.md.
-- Aplicar primeiro em DEV, depois em PROD.

-- ---------------------------------------------------------------------------
-- Extensões
-- ---------------------------------------------------------------------------
create extension if not exists pgcrypto;   -- gen_random_uuid() para PKs UUID
create extension if not exists citext;     -- email case-insensitive (usado em profiles, Fase 1)

-- ---------------------------------------------------------------------------
-- Utilitário compartilhado: manter updated_at
-- Decisão de offline/sync: TODA tabela editável carrega updated_at e usa este trigger.
-- (As tabelas em si entram a partir da Fase 1.)
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

comment on function public.set_updated_at() is
  'Trigger BEFORE UPDATE: seta updated_at = now(). Padrão para todas as tabelas editáveis.';

-- Exemplo de uso (referência para a Fase 1; não cria nada agora):
--   create trigger trg_set_updated_at
--   before update on public.<tabela>
--   for each row execute function public.set_updated_at();
