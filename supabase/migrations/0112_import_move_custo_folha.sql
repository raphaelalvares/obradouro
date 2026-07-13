-- 0112_import_move_custo_folha.sql  (EAP — import respeita o invariante "custo mora na folha")
--
-- BUG: o create manual de tarefa empurra o custo do pai pra baixo (_mover_custo), mas a RPC
-- importar_checklist NÃO. Cenário: arquiteto cria à mão a etapa "Alvenaria" como FOLHA com custo
-- (lump-sum) e depois importa uma planilha cuja etapa normaliza pro mesmo nome_norm → a RPC anexa
-- tarefas à etapa existente, que passa a ter custo_total E filhos. Isso quebra o invariante ("custo
-- só na folha"): o rollup do front/PDF ignora o custo do pai quando há filhos (o lump-sum SOME do
-- orçamento) e atualizar_etapa_detalhes passa a dar 422 (tem_filhos), travando a correção.
--
-- FIX: ao anexar a 1ª tarefa NOVA a uma etapa que ainda era folha-com-custo, empurra o custo da etapa
-- pra essa 1ª tarefa (se ela não trouxe custo próprio da planilha) e ZERA a etapa. Se a 1ª tarefa já
-- veio custeada (orçamento itemizado), o detalhamento importado prevalece e a etapa só zera — em
-- ambos os casos o invariante volta a valer. Idêntica à 0081, só com esse bloco a mais.
--
-- Aplicar como postgres (é SECURITY DEFINER owner=postgres). DEV antes de PROD.

begin;

create or replace function public.importar_checklist(p_obra uuid, p_payload jsonb)
returns table (etapas_novas int, etapas_existentes int, itens_novos int, itens_existentes int)
language plpgsql security definer set search_path = '' as $$
declare
  v_uid       uuid := (select auth.uid());
  v_tenant    uuid;
  v_etapa     jsonb;
  v_item      jsonb;
  v_etapa_id  uuid;
  v_nn        text;
  v_inn       text;
  v_seq       bigint;
  -- move-down do custo da etapa-folha existente p/ a 1ª tarefa importada
  v_folha_custo boolean;
  v_primeiro    uuid;
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

    -- a etapa ainda era FOLHA-com-custo (lump-sum manual, sem subetapa/tarefa)? Se sim, o custo terá
    -- de descer p/ a 1ª tarefa importada (mantém "custo na folha"). Etapa recém-criada: sempre false.
    select (e.custo_total is not null or e.custo_material is not null or e.custo_mao_obra is not null
            or e.valor_unitario is not null or e.mao_obra_unitaria is not null)
           and not exists (select 1 from public.subetapas s where s.etapa_id = e.id)
           and not exists (select 1 from public.checklist_itens c where c.etapa_id = e.id)
      into v_folha_custo
    from public.etapas e where e.id = v_etapa_id;
    v_primeiro := null;

    for v_item in select * from jsonb_array_elements(coalesce(v_etapa->'itens', '[]'::jsonb)) loop
      v_inn := coalesce(v_item->>'nome_norm', '');
      if v_inn = '' then continue; end if;

      -- dedupe no MESMO escopo da tarefa direto-na-etapa (parent null + subetapa null), casando com
      -- o índice parcial uq_itens_etapa_nomenorm_top da 0081.
      if exists (select 1 from public.checklist_itens ci
                 where ci.etapa_id = v_etapa_id and ci.nome_norm = v_inn
                       and ci.parent_item_id is null and ci.subetapa_id is null) then
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
        if v_primeiro is null then v_primeiro := (v_item->>'id')::uuid; end if;
        perform public.cria_audit_log(null, null, p_obra, 'item.criado', 'checklist_item',
                                      (v_item->>'id')::uuid, null::jsonb, v_item->>'nome', v_seq,
                                      null);
      exception when unique_violation then
        itens_existentes := itens_existentes + 1;
      end;
    end loop;

    -- move-down do custo: a etapa deixou de ser folha (ganhou a 1ª tarefa). O lump-sum desce p/ a 1ª
    -- tarefa importada SE ela não trouxe custo próprio; senão o itemizado prevalece. A etapa sempre
    -- zera → o rollup volta a fechar e a edição destrava.
    if v_folha_custo and v_primeiro is not null then
      update public.checklist_itens t
         set unidade = e.unidade, quantidade = e.quantidade,
             valor_unitario = e.valor_unitario, mao_obra_unitaria = e.mao_obra_unitaria,
             custo_mao_obra = e.custo_mao_obra, custo_material = e.custo_material,
             custo_total = e.custo_total
        from public.etapas e
       where t.id = v_primeiro and e.id = v_etapa_id and t.custo_total is null;
      update public.etapas
         set unidade = null, quantidade = null, valor_unitario = null, mao_obra_unitaria = null,
             custo_mao_obra = null, custo_material = null, custo_total = null
       where id = v_etapa_id;
    end if;
  end loop;

  return next;
end;
$$;
alter function public.importar_checklist(uuid, jsonb) owner to postgres;
revoke all on function public.importar_checklist(uuid, jsonb) from public, anon;
grant execute on function public.importar_checklist(uuid, jsonb) to authenticated;

commit;
