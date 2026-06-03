-- 0031_anexos_guard.sql  (Fase 4 — CORE: regra fina que a RLS nao expressa)
-- Espelha etapas_guard/checklist_itens_guard (0025). Dispara ANTES do trigger de seq (nome
-- 'trg_anexos_guard' < 'trg_anexos_seq'): coerencia de tenant/obra/parent validada antes de alocar seq.
-- Owner postgres; SECURITY DEFINER p/ ler obras/etapas/itens/obra_membros sob RLS.
--   INSERT: tenant/obra coerentes; parent (etapa|item) pertence a MESMA obra; quem executa (arq/prest).
--   UPDATE: bloqueado p/ todos (anexo e imutavel — sem grant de update no 0030; aqui e cinto extra).
--   DELETE: arquiteto apaga qualquer um; prestador SO o que ele mesmo subiu (criado_por = auth.uid());
--           cliente/nao-membro = nada.
create or replace function public.anexos_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    -- parent pertence a obra do anexo (coerencia da FK polimorfica)
    if new.parent_type = 'etapa' then
      if not exists (select 1 from public.etapas e
                     where e.id = new.parent_id and e.obra_id = new.obra_id) then
        raise exception 'etapa do anexo nao pertence a obra' using errcode = '23514';
      end if;
    elsif new.parent_type = 'checklist_item' then
      if not exists (select 1 from public.checklist_itens i
                     where i.id = new.parent_id and i.obra_id = new.obra_id) then
        raise exception 'item do anexo nao pertence a obra' using errcode = '23514';
      end if;
    else
      raise exception 'parent_type invalido' using errcode = '23514';
    end if;
    if not public.pode_executar_obra(new.obra_id) then
      raise exception 'apenas quem executa a obra pode anexar' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    raise exception 'anexo e imutavel (apague e suba outro)' using errcode = '42501';
  end if;

  -- DELETE
  v_papel := public.meu_papel_obra(old.obra_id);
  if v_papel = 'arquiteto' then
    return old;
  elsif v_papel = 'prestador' then
    if old.criado_por is distinct from (select auth.uid()) then
      raise exception 'prestador so apaga o proprio anexo' using errcode = '42501';
    end if;
    return old;
  else
    raise exception 'sem permissao para apagar anexo' using errcode = '42501';  -- cliente/nao-membro
  end if;
end;
$$;
alter function public.anexos_guard() owner to postgres;
drop trigger if exists trg_anexos_guard on public.anexos;
create trigger trg_anexos_guard
  before insert or update or delete on public.anexos
  for each row execute function public.anexos_guard();
