-- 0102_acesso_cliente_da_oportunidade.sql  (costura Comercial ↔ Portal: o MESMO cliente do lead)
--
-- Antes, o cliente do portal era emendado ao lead só por e-mail SOLTO: `oportunidades.contato_email`
-- era `text` puro e `acessos_cliente.email` é `citext` → diferença de caixa/espaço quebrava o casamento
-- em silêncio, e não havia como saber "de qual lead é este acesso" sem pular por projeto/obra.
--
-- Esta migration fecha a costura barata (sem tabela `clientes` nova):
--   (1) `oportunidades.contato_email` → `citext` (case-insensitive, igual ao portal);
--   (2) `acessos_cliente.oportunidade_id` → FK REAL de volta ao lead (antes inexistente);
--   (3) guard revalida o novo elo (coerência de tenant no INSERT; mutável só p/ null [ON DELETE SET
--       NULL] ou p/ opp do mesmo tenant no UPDATE);
--   (4) backfill dos acessos já existentes que casam com um lead (via projeto_id/obra_id).
--
-- Depende de: 0058 (oportunidades), 0089 (acessos_cliente + guard). Aplicar como postgres, após 0101.
-- DEV antes de PROD.

begin;

-- ===================== (1) contato_email → citext (casa com acessos_cliente.email) =====================
-- Idempotente: só altera quando ainda não for citext. Não há índice/constraint/guard sobre a coluna
-- (o oportunidades_guard não referencia contato_email) → troca de tipo sem efeito colateral.
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'oportunidades'
      and column_name = 'contato_email' and udt_name <> 'citext'
  ) then
    alter table public.oportunidades
      alter column contato_email type citext using contato_email::citext;
  end if;
end $$;

-- ===================== (2) elo real acesso → lead =====================
-- ON DELETE SET NULL: excluir o lead NÃO derruba o acesso do cliente (o portal segue vivo pela
-- obra/projeto). Índice parcial p/ o lookup "acessos deste lead".
alter table public.acessos_cliente
  add column if not exists oportunidade_id uuid references public.oportunidades(id) on delete set null;
create index if not exists ix_acessos_cliente_oportunidade
  on public.acessos_cliente (oportunidade_id) where oportunidade_id is not null;

-- ===================== (3) guard: valida o novo elo (recria a função inteira; idempotente) =====================
-- INSERT: oportunidade_id (se houver) tem de ser do MESMO tenant (anti cross-tenant, espelha
-- projeto_id/obra_id). UPDATE: identidade segue imutável, MAS oportunidade_id pode mudar p/ null
-- (o ON DELETE SET NULL precisa poder zerar) ou p/ uma opp do mesmo tenant (backfill/re-vínculo);
-- torná-lo imutável travaria a exclusão do lead. O trigger trg_acessos_cliente_guard já aponta p/ cá.
create or replace function public.acessos_cliente_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if new.tenant_id is distinct from (select auth.uid()) then
      raise exception 'tenant_id incoerente' using errcode = '42501';
    end if;
    if new.projeto_id is not null and not exists (
         select 1 from public.projetos p where p.id = new.projeto_id and p.tenant_id = new.tenant_id) then
      raise exception 'projeto de outro tenant' using errcode = '42501';
    end if;
    if new.obra_id is not null and not exists (
         select 1 from public.obras o where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'obra de outro tenant' using errcode = '42501';
    end if;
    if new.oportunidade_id is not null and not exists (
         select 1 from public.oportunidades op
         where op.id = new.oportunidade_id and op.tenant_id = new.tenant_id) then
      raise exception 'oportunidade de outro tenant' using errcode = '42501';
    end if;
    return new;
  end if;
  if tg_op = 'UPDATE' then
    -- identidade imutável (email comparado como text: sob search_path='' o operador citext do schema
    -- da extensão não resolve; ::text é binário e =/lower de text são pg_catalog).
    if new.id is distinct from old.id
       or new.tenant_id is distinct from old.tenant_id
       or new.projeto_id is distinct from old.projeto_id
       or new.obra_id is distinct from old.obra_id
       or new.email::text is distinct from old.email::text
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade do acesso e imutavel' using errcode = '42501';
    end if;
    -- oportunidade_id: pode ir a null (FK set null) ou p/ uma opp do MESMO tenant; nunca p/ outro tenant.
    if new.oportunidade_id is distinct from old.oportunidade_id
       and new.oportunidade_id is not null
       and not exists (select 1 from public.oportunidades op
                       where op.id = new.oportunidade_id and op.tenant_id = new.tenant_id) then
      raise exception 'oportunidade de outro tenant' using errcode = '42501';
    end if;
    return new;
  end if;
  return old;  -- DELETE
end;
$$;
alter function public.acessos_cliente_guard() owner to postgres;

-- ===================== (4) backfill: liga os acessos já existentes ao lead correspondente =====================
-- Só onde ainda está null. Casa por projeto_id OU obra_id do MESMO tenant (ambos 1:1 com a opp →
-- no máx. 1 match; scalar subquery + limit 1 é defesa contra empate improvável). Idempotente.
update public.acessos_cliente ac
set oportunidade_id = (
      select op.id from public.oportunidades op
      where op.tenant_id = ac.tenant_id
        and ( (ac.projeto_id is not null and op.projeto_id = ac.projeto_id)
           or (ac.obra_id   is not null and op.obra_id   = ac.obra_id) )
      limit 1)
where ac.oportunidade_id is null
  and exists (
      select 1 from public.oportunidades op
      where op.tenant_id = ac.tenant_id
        and ( (ac.projeto_id is not null and op.projeto_id = ac.projeto_id)
           or (ac.obra_id   is not null and op.obra_id   = ac.obra_id) ));

commit;
