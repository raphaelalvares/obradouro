-- 0043_checklist_orcamento_ambiente.sql  (Fase 6-prep — adapta o checklist ao modelo real do usuario)
-- Decisoes do usuario (2026-06-03), a partir do Excel de orcamento + PDF de checklist reais:
--  (1) o import do .xlsx de ORCAMENTO traz etapas + servicos (XX.YY) como tarefas + VALORES
--      (unidade/quantidade/mao-de-obra/material/total) -> base p/ um futuro modulo de orcamento.
--  (2) cada tarefa ganha um campo OPCIONAL 'ambiente' (comodo: Cozinha, Banheiro...) p/ a UI
--      agrupar como no checklist real deles, SEM 3o nivel rigido.
-- Tudo ADITIVO/idempotente. Nao mexe em seq/RLS/policies. So: colunas novas + guard (vira allowlist
-- de verdade) + RPC de import (passa a gravar os campos novos nos itens NOVOS).

-- ============ (1) COLUNAS NOVAS em checklist_itens (todas OPCIONAIS) ============
alter table public.checklist_itens
  add column if not exists ambiente        text,            -- comodo p/ agrupar na UI (opcional)
  add column if not exists unidade         text,            -- un/m2/verba/pontos... (do orcamento)
  add column if not exists quantidade      numeric(14,3),   -- qtd do orcamento
  add column if not exists custo_mao_obra  numeric(14,2),   -- M.O (R$)
  add column if not exists custo_material  numeric(14,2),   -- MAT (R$)
  add column if not exists custo_total     numeric(14,2);   -- TOTAL = MO + MAT (R$)

-- agrupar por ambiente dentro da etapa (case/acento a cargo do app; aqui cru). NULLs nao indexam muito.
create index if not exists ix_itens_etapa_ambiente
  on public.checklist_itens (etapa_id, ambiente);

-- ============ (2) GUARD vira ALLOWLIST de verdade (protege as colunas novas do prestador) ============
-- O 0025 dizia "allowlist" mas implementava um DENYLIST (lista fixa nome/nome_norm/ordem/seq_humano),
-- entao colunas novas escapariam p/ o prestador. Agora: prestador so pode variar
-- estado/concluido_por/concluido_em (e updated_at do trigger); QUALQUER outra coluna (inclui
-- ambiente/valores) e imutavel p/ prestador. Comparacao via to_jsonb cobre colunas futuras sozinha.
-- O resto da funcao e identico ao 0025 (mesmos checks de INSERT/identidade/DELETE).
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
      return new;                                     -- arquiteto: tudo (nome/estado/ordem/ambiente/valores)
    elsif v_papel = 'prestador' then
      -- ALLOWLIST real: so estado/conclusao (e updated_at do trigger) podem variar; resto imutavel.
      if (to_jsonb(new) - 'estado' - 'concluido_por' - 'concluido_em' - 'updated_at')
         is distinct from
         (to_jsonb(old) - 'estado' - 'concluido_por' - 'concluido_em' - 'updated_at') then
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
-- o trigger trg_itens_guard ja existe (0025) e aponta p/ esta funcao; create or replace basta.

-- ============ (3) IMPORT: grava ambiente + valores nos itens NOVOS ============
-- Idempotencia INALTERADA (dedupe por nome_norm; item existente NAO e tocado, inclusive valores).
-- O payload do item agora aceita campos OPCIONAIS: ambiente, unidade, quantidade,
-- custo_mao_obra, custo_material, custo_total. Etapa segue SEM valores (subtotal e derivado/somado).
create or replace function public.importar_checklist(p_obra uuid, p_payload jsonb)
returns table (etapas_novas int, etapas_existentes int, itens_novos int, itens_existentes int)
language plpgsql security definer set search_path = '' as $$
declare
  v_uid      uuid := (select auth.uid());
  v_tenant   uuid;
  v_etapa    jsonb;
  v_item     jsonb;
  v_etapa_id uuid;
  v_nn       text;
  v_inn      text;
  v_seq      bigint;
begin
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;
  if jsonb_typeof(p_payload) is distinct from 'array' then
    raise exception 'payload de import invalido' using errcode = '22023';
  end if;

  select o.tenant_id into v_tenant from public.obras o where o.id = p_obra;
  if v_tenant is null then
    raise exception 'obra inexistente' using errcode = 'P0002';
  end if;
  if not public.is_arquiteto_ativo(p_obra) then
    raise exception 'apenas arquiteto pode importar' using errcode = '42501';
  end if;

  -- serializa imports da MESMA obra (transaction-scoped); fecha a corrida do etapa_id NULL.
  perform pg_advisory_xact_lock(hashtext('cria:import_checklist'), hashtext(p_obra::text));

  etapas_novas := 0; etapas_existentes := 0; itens_novos := 0; itens_existentes := 0;

  for v_etapa in select * from jsonb_array_elements(p_payload) loop
    v_nn := coalesce(v_etapa->>'nome_norm', '');
    if v_nn = '' then continue; end if;

    select e.id into v_etapa_id
    from public.etapas e where e.obra_id = p_obra and e.nome_norm = v_nn;

    if v_etapa_id is null then
      begin
        insert into public.etapas (id, obra_id, tenant_id, nome, nome_norm, ordem)
        values ((v_etapa->>'id')::uuid, p_obra, v_tenant,
                v_etapa->>'nome', v_nn, coalesce((v_etapa->>'ordem')::int, 0))
        returning id, seq_humano into v_etapa_id, v_seq;
        etapas_novas := etapas_novas + 1;
        perform public.cria_audit_log(null, null, p_obra, 'etapa.criada', 'etapa',
                                      v_etapa_id, null::jsonb, v_etapa->>'nome', v_seq, null);
      exception when unique_violation then
        select e.id into v_etapa_id
        from public.etapas e where e.obra_id = p_obra and e.nome_norm = v_nn;
        etapas_existentes := etapas_existentes + 1;
      end;
    else
      etapas_existentes := etapas_existentes + 1;
    end if;

    for v_item in select * from jsonb_array_elements(coalesce(v_etapa->'itens', '[]'::jsonb)) loop
      v_inn := coalesce(v_item->>'nome_norm', '');
      if v_inn = '' then continue; end if;

      if exists (select 1 from public.checklist_itens ci
                 where ci.etapa_id = v_etapa_id and ci.nome_norm = v_inn) then
        itens_existentes := itens_existentes + 1;
        continue;
      end if;

      begin
        insert into public.checklist_itens
          (id, etapa_id, obra_id, tenant_id, nome, nome_norm, ordem,
           ambiente, unidade, quantidade, custo_mao_obra, custo_material, custo_total)
        values ((v_item->>'id')::uuid, v_etapa_id, p_obra, v_tenant,
                v_item->>'nome', v_inn, coalesce((v_item->>'ordem')::int, 0),
                nullif(v_item->>'ambiente', ''),
                nullif(v_item->>'unidade', ''),
                nullif(v_item->>'quantidade', '')::numeric,
                nullif(v_item->>'custo_mao_obra', '')::numeric,
                nullif(v_item->>'custo_material', '')::numeric,
                nullif(v_item->>'custo_total', '')::numeric)
        returning seq_humano into v_seq;
        itens_novos := itens_novos + 1;
        perform public.cria_audit_log(null, null, p_obra, 'item.criado', 'checklist_item',
                                      (v_item->>'id')::uuid, null::jsonb, v_item->>'nome', v_seq, null);
      exception when unique_violation then
        itens_existentes := itens_existentes + 1;
      end;
    end loop;
  end loop;

  return next;
end;
$$;
alter function public.importar_checklist(uuid, jsonb) owner to postgres;
revoke all on function public.importar_checklist(uuid, jsonb) from public, anon;
grant execute on function public.importar_checklist(uuid, jsonb) to authenticated;
