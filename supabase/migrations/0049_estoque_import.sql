-- 0049_estoque_import.sql  (Fase 6 — import idempotente da NF-e)
-- O backend faz o parse do XML (xml.etree), gera UUIDs (nota + cada item) e chama esta funcao com o
-- payload jsonb:
--   {"id":"<uuid>","chave":"<44 digitos>","numero":"123","serie":"1",
--    "emitente_nome":"...","emitente_cnpj":"...","data_emissao":"2026-..T..","valor_total":1234.56,
--    "xml":"<...>","itens":[{"id":"<uuid>","codigo":"..","descricao":"..","ncm":"..","unidade":"UN",
--                           "quantidade_nota":10,"valor_unitario":1.23,"valor_total":12.30,"ordem":1}]}
-- SECURITY DEFINER (owner postgres): isenta de RLS, mas valida arquiteto ativo internamente.
--
-- IDEMPOTENCIA (ponto "g" do review) = chave de acesso por tenant: reimportar o MESMO XML devolve a
-- nota existente com criada=false e itens_novos=0 (NAO duplica estoque). NAO usa ON CONFLICT na nota
-- (queimaria seq via trigger 0046): exists-check pela chave; a rara corrida cai no EXCEPTION
-- (subtransacao -> rollback do INSERT e do seq). Advisory lock por chave serializa imports concorrentes.
-- AUDITORIA: emite 'nota.importada' (cria_audit_log 10-arg, escopo obra).
create or replace function public.importar_nfe(p_obra uuid, p_payload jsonb)
returns table (nota_id uuid, criada boolean, itens_novos int)
language plpgsql security definer set search_path = '' as $$
declare
  v_uid    uuid := (select auth.uid());
  v_tenant uuid;
  v_chave  text;
  v_nota   uuid;
  v_seq    bigint;
  v_item   jsonb;
  v_count  int := 0;
begin
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;
  if jsonb_typeof(p_payload) is distinct from 'object' then
    raise exception 'payload de import invalido' using errcode = '22023';
  end if;
  v_chave := coalesce(p_payload->>'chave', '');
  if v_chave !~ '^[0-9]{44}$' then
    raise exception 'chave de acesso invalida' using errcode = '22023';
  end if;

  select o.tenant_id into v_tenant from public.obras o where o.id = p_obra;
  if v_tenant is null then
    raise exception 'obra inexistente' using errcode = 'P0002';
  end if;
  if not public.is_arquiteto_ativo(p_obra) then
    raise exception 'apenas arquiteto pode importar' using errcode = '42501';
  end if;

  -- serializa imports concorrentes da MESMA chave (transaction-scoped)
  perform pg_advisory_xact_lock(hashtext('cria:import_nfe'), hashtext(v_chave));

  -- idempotencia: nota ja existe p/ esse tenant+chave => devolve sem duplicar
  select n.id into v_nota
  from public.notas_fiscais n
  where n.tenant_id = v_tenant and n.chave_acesso = v_chave;
  if v_nota is not null then
    nota_id := v_nota; criada := false; itens_novos := 0;
    return next; return;
  end if;

  begin
    insert into public.notas_fiscais
      (id, obra_id, tenant_id, chave_acesso, numero, serie, emitente_nome, emitente_cnpj,
       data_emissao, valor_total, xml, created_by)
    values
      ((p_payload->>'id')::uuid, p_obra, v_tenant, v_chave,
       p_payload->>'numero', p_payload->>'serie',
       p_payload->>'emitente_nome', p_payload->>'emitente_cnpj',
       (p_payload->>'data_emissao')::timestamptz,
       coalesce((p_payload->>'valor_total')::numeric, 0),
       p_payload->>'xml', v_uid)
    returning id, seq_humano into v_nota, v_seq;
  exception when unique_violation then
    -- corrida: outra txn inseriu a mesma chave (uq_notas_tenant_chave) ou o mesmo uuid; trata existente
    select n.id into v_nota
    from public.notas_fiscais n
    where n.tenant_id = v_tenant and n.chave_acesso = v_chave;
    nota_id := v_nota; criada := false; itens_novos := 0;
    return next; return;
  end;

  for v_item in select * from jsonb_array_elements(coalesce(p_payload->'itens', '[]'::jsonb)) loop
    insert into public.nota_itens
      (id, nota_id, obra_id, tenant_id, codigo, descricao, ncm, unidade,
       quantidade_nota, valor_unitario, valor_total, ordem)
    values
      ((v_item->>'id')::uuid, v_nota, p_obra, v_tenant,
       v_item->>'codigo', coalesce(v_item->>'descricao', '(sem descricao)'),
       v_item->>'ncm', v_item->>'unidade',
       coalesce((v_item->>'quantidade_nota')::numeric, 0),
       (v_item->>'valor_unitario')::numeric,
       (v_item->>'valor_total')::numeric,
       coalesce((v_item->>'ordem')::int, 0));
    v_count := v_count + 1;
  end loop;

  perform public.cria_audit_log(
    null, null, p_obra, 'nota.importada', 'nota_fiscal', v_nota,
    jsonb_build_object('chave', v_chave, 'itens', v_count, 'valor_total', p_payload->>'valor_total'),
    coalesce(nullif(p_payload->>'numero', ''), v_chave), v_seq, null);

  nota_id := v_nota; criada := true; itens_novos := v_count;
  return next;
end;
$$;
alter function public.importar_nfe(uuid, jsonb) owner to postgres;
revoke all on function public.importar_nfe(uuid, jsonb) from public, anon;
grant execute on function public.importar_nfe(uuid, jsonb) to authenticated;
