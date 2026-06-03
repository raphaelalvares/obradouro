-- 0044_checklist_subitens.sql  (Fase 6-prep — sub-checklist por tarefa)
-- Decisao do usuario (2026-06-03): cada SERVICO importado (tarefa-pai, com valores) pode ter N
-- itens de checklist criados a MAO (os checkboxes reais). 3 niveis: etapa -> tarefa -> sub-item.
-- Modelo: AUTO-REFERENCIA em checklist_itens (parent_item_id). Pai = parent_item_id NULL (do import,
-- carrega valores); filho = parent_item_id setado (manual). Trava em 2 niveis de item (filho nao
-- vira pai). Pai = "cabecalho com progresso": so os filhos tem estado; a UI soma o progresso.
-- Aditivo/idempotente. Reescreve guard + import (create or replace) p/ ficarem cientes do parent.

-- ===================== (1) coluna auto-referente + indice =====================
alter table public.checklist_itens
  add column if not exists parent_item_id uuid
    references public.checklist_itens(id) on delete cascade;

create index if not exists ix_itens_parent on public.checklist_itens (parent_item_id);

-- ===================== (2) dedupe por NIVEL =====================
-- O indice antigo (etapa_id, nome_norm) sobre TODAS as linhas barraria nomes iguais sob pais
-- diferentes (e um filho com o mesmo nome de um top-level). Trocamos por 2 indices parciais:
--   - top-level (parent NULL): nome unico POR ETAPA;
--   - filhos (parent setado):  nome unico POR PAI.
drop index if exists public.uq_itens_etapa_nomenorm;
create unique index if not exists uq_itens_etapa_nomenorm_top
  on public.checklist_itens (etapa_id, nome_norm) where parent_item_id is null;
create unique index if not exists uq_itens_parent_nomenorm
  on public.checklist_itens (parent_item_id, nome_norm) where parent_item_id is not null;

-- ===================== (3) GUARD ciente do parent =====================
-- Acrescenta ao 0043: no INSERT de sub-item, valida que o pai existe, e da MESMA etapa/obra, e que
-- o pai e top-level (trava 2 niveis); e torna parent_item_id IMUTAVEL (sem reparent). Mantem a
-- allowlist real do prestador (to_jsonb): so estado/conclusao mudam (parent_item_id fica imutavel).
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
    -- sub-item: pai precisa existir, na mesma etapa/obra, e ser top-level (so 2 niveis de item).
    if new.parent_item_id is not null then
      if not exists (select 1 from public.checklist_itens pai
                     where pai.id = new.parent_item_id
                       and pai.etapa_id = new.etapa_id
                       and pai.obra_id = new.obra_id
                       and pai.parent_item_id is null) then
        raise exception 'sub-item: pai invalido (outra etapa/obra ou ja e sub-item)'
          using errcode = '23514';
      end if;
    end if;
    if not public.is_arquiteto_ativo(new.obra_id) then
      raise exception 'apenas arquiteto pode criar item' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    -- identidade/escopo (inclui o pai) nunca mudam por UPDATE (vale ate p/ arquiteto)
    if new.id is distinct from old.id
       or new.tenant_id is distinct from old.tenant_id
       or new.obra_id  is distinct from old.obra_id
       or new.etapa_id is distinct from old.etapa_id
       or new.parent_item_id is distinct from old.parent_item_id
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade/escopo do item sao imutaveis' using errcode = '42501';
    end if;

    v_papel := public.meu_papel_obra(old.obra_id);
    if v_papel = 'arquiteto' then
      return new;
    elsif v_papel = 'prestador' then
      if (to_jsonb(new) - 'estado' - 'concluido_por' - 'concluido_em' - 'updated_at')
         is distinct from
         (to_jsonb(old) - 'estado' - 'concluido_por' - 'concluido_em' - 'updated_at') then
        raise exception 'prestador so pode alterar o estado do item' using errcode = '42501';
      end if;
      return new;
    else
      raise exception 'sem permissao para alterar item' using errcode = '42501';
    end if;
  end if;

  if not public.is_arquiteto_ativo(old.obra_id) then
    raise exception 'apenas arquiteto pode remover item' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.checklist_itens_guard() owner to postgres;

-- ===================== (4) IMPORT ciente do parent =====================
-- Igual ao 0043, mudando UMA coisa: o exists-check de item passa a olhar SO os top-level
-- (parent_item_id is null), p/ um sub-item com mesmo nome nao mascarar a 1a importacao do servico.
-- O import continua criando SO tarefas-pai (parent_item_id default NULL).
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
                 where ci.etapa_id = v_etapa_id and ci.nome_norm = v_inn
                       and ci.parent_item_id is null) then
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
