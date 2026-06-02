-- 0026_checklist_import.sql  (Fase 3 — import idempotente do template)
-- O backend (openpyxl) le o .xlsx de colunas FIXAS, normaliza (nome_norm, MESMA fn do create manual),
-- gera um UUID por no e chama esta funcao com o payload jsonb:
--   [{"id":"<uuid>","nome":"Fundacao","nome_norm":"fundacao","ordem":1,
--     "itens":[{"id":"<uuid>","nome":"Sapatas","nome_norm":"sapatas","ordem":1}, ...]}, ...]
-- SECURITY DEFINER (owner postgres): isenta de RLS, mas valida arquiteto ativo internamente.
--
-- IDEMPOTENCIA: dedupe por chave natural (obra,nome_norm)/(etapa,nome_norm). Reimportar o MESMO
-- template => 0 novas (linhas existentes sao PULADAS, nao reinseridas) e NAO renumera nem reseta
-- estado de item (linha existente nao e tocada). NAO usa ON CONFLICT (que queimaria seq via trigger):
-- checa existencia e so insere linha nova; o raro conflito concorrente (vs create manual do mesmo
-- nome) cai no EXCEPTION (subtransacao -> rollback do INSERT e do seq, sem queima).
-- CONCORRENCIA: advisory lock por obra serializa imports da MESMA obra (em READ COMMITTED, o 2o
-- import ja enxerga as linhas commitadas do 1o -> resolve etapa_id sem o buraco de "NULL etapa_id").
-- AUDITORIA: emite etapa.criada/item.criado por linha NOVA (identidade derivada por cria_audit_log).
-- LIMITE conhecido: a chave e o nome ATUAL; se o arquiteto renomear uma etapa no app e reimportar o
-- template original, a etapa volta a ser criada (documentado em docs/fase3-design.md).
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
        -- create manual concorrente do mesmo nome: trata como existente (subtxn ja reverteu o seq).
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
          (id, etapa_id, obra_id, tenant_id, nome, nome_norm, ordem)   -- estado usa default 'pendente'
        values ((v_item->>'id')::uuid, v_etapa_id, p_obra, v_tenant,
                v_item->>'nome', v_inn, coalesce((v_item->>'ordem')::int, 0))
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
