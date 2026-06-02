-- 0025_checklist_guards.sql  (Fase 3 — CORE: camada 2 da regra fina que a RLS nao expressa)
-- Espelha obra_membros_guard (0019). Travas por-coluna + imutabilidade + coerencia do denormalizado.
-- Disparam ANTES dos triggers de seq (nome '..._guard' < '..._seq'): assim a coerencia de tenant_id
-- e validada antes de o seq ser alocado. Owner postgres; SECURITY DEFINER p/ ler obras/obra_membros.

-- (A) ETAPAS: create/rename/reorder/delete SO arquiteto ativo; tenant/obra coerentes e imutaveis.
create or replace function public.etapas_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo(new.obra_id) then
      raise exception 'apenas arquiteto pode criar etapa' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    if new.id is distinct from old.id
       or new.tenant_id is distinct from old.tenant_id
       or new.obra_id  is distinct from old.obra_id
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade da etapa e imutavel' using errcode = '42501';
    end if;
    if not public.is_arquiteto_ativo(old.obra_id) then
      raise exception 'apenas arquiteto pode alterar etapa' using errcode = '42501';
    end if;
    return new;
  end if;

  -- DELETE
  if not public.is_arquiteto_ativo(old.obra_id) then
    raise exception 'apenas arquiteto pode remover etapa' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.etapas_guard() owner to postgres;
drop trigger if exists trg_etapas_guard on public.etapas;
create trigger trg_etapas_guard
  before insert or update or delete on public.etapas
  for each row execute function public.etapas_guard();

-- (B) ITENS: arquiteto = tudo; prestador = SO estado (+ atribuicao de conclusao); cliente/nao-membro
-- = nada. id/tenant/obra/etapa IMUTAVEIS p/ TODOS (anti-sequestro cross-obra/cross-etapa; mover item
-- de etapa esta FORA do escopo da Fase 3 — arquiteto recria). INSERT/DELETE so arquiteto.
-- Prestador usa ALLOWLIST (so 'estado','concluido_por','concluido_em' podem variar) — qualquer coluna
-- nova futura fica travada p/ prestador por padrao, ate ser liberada de proposito.
create or replace function public.checklist_itens_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    if not exists (select 1 from public.etapas e
                   where e.id = new.etapa_id and e.obra_id = new.obra_id) then
      raise exception 'etapa nao pertence a obra do item' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo(new.obra_id) then
      raise exception 'apenas arquiteto pode criar item' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    -- identidade/escopo nunca mudam por UPDATE (vale ate p/ arquiteto)
    if new.id is distinct from old.id
       or new.tenant_id is distinct from old.tenant_id
       or new.obra_id  is distinct from old.obra_id
       or new.etapa_id is distinct from old.etapa_id
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade/escopo do item sao imutaveis' using errcode = '42501';
    end if;

    v_papel := public.meu_papel_obra(old.obra_id);
    if v_papel = 'arquiteto' then
      return new;                                     -- nome/estado/ordem/conclusao livres
    elsif v_papel = 'prestador' then
      -- ALLOWLIST: so estado/concluido_por/concluido_em podem mudar; o resto e imutavel.
      if new.nome      is distinct from old.nome
         or new.nome_norm  is distinct from old.nome_norm
         or new.ordem      is distinct from old.ordem
         or new.seq_humano is distinct from old.seq_humano then
        raise exception 'prestador so pode alterar o estado do item' using errcode = '42501';
      end if;
      return new;
    else
      raise exception 'sem permissao para alterar item' using errcode = '42501';  -- cliente/nao-membro
    end if;
  end if;

  -- DELETE: so arquiteto
  if not public.is_arquiteto_ativo(old.obra_id) then
    raise exception 'apenas arquiteto pode remover item' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.checklist_itens_guard() owner to postgres;
drop trigger if exists trg_itens_guard on public.checklist_itens;
create trigger trg_itens_guard
  before insert or update or delete on public.checklist_itens
  for each row execute function public.checklist_itens_guard();
