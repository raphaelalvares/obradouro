-- 0057_etapas_concluida.sql
-- Conclusão de ETAPA (marco). Permite marcar uma etapa como concluída — pensado p/ etapas SEM
-- tarefas, que não têm checklist p/ derivar a conclusão. Alimenta o status do Gantt (verde/vermelho).
-- Só ARQUITETO altera: a RLS (etapas_update, 0024) e o etapas_guard (0025) já exigem arquiteto p/
-- QUALQUER update de etapa, e 'concluida' não está na lista de campos imutáveis do guard — então
-- NÃO é preciso mexer em guard nem RLS.
--
-- Eu GERO, você APLICA no Supabase como postgres. APLICAR ANTES de subir o backend (o checklist
-- passa a LER estas colunas; sem elas, as leituras de etapa quebram). DEV antes de PROD.

alter table public.etapas
  add column if not exists concluida     boolean     not null default false,
  add column if not exists concluida_em  timestamptz,
  add column if not exists concluida_por uuid references public.profiles(id) on delete set null;
