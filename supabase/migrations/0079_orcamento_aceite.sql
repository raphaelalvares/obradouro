-- 0079_orcamento_aceite.sql  (Orçamento: cliente APROVA/RECUSA/PEDE ALTERAÇÃO no portal)
--
-- Fecha o ciclo comercial: o cliente decide a proposta ENVIADA → registra a decisão na versão,
-- avança a oportunidade vinculada p/ 'ganho' (quando aprovado) e o backend notifica o arquiteto
-- (histórico + e-mail). Amarra lead → orçamento → projeto → obra.
--
-- DESAFIO: a decisão é uma escrita do CLIENTE em domínios do ARQUITETO. Os dois guards barram
-- não-dono (orcamento_versoes_guard exige arquiteto; oportunidades_guard exige tenant=auth.uid). A
-- RLS também barra o acesso DIRETO do cliente (orcamento_versoes é arquiteto-only; oportunidades é
-- dono-only) — então a única via é a RPC SECURITY DEFINER abaixo, que valida a legitimidade. Para a
-- RPC conseguir gravar, cada guard ganha UMA exceção estreita (só as colunas da ação, papel=cliente
-- do projeto). Como a RLS já bloqueia o caminho direto, a exceção do guard só é alcançável pela RPC.
--
-- Depende de: 0060 (orcamento), 0058/0059 (oportunidades + projeto_id), 0036 (papel/ids do projeto),
-- 0071 (cria_audit_log com membership). Aplicar como postgres, após 0078.

-- ===================== (1) colunas de decisão =====================
alter table public.orcamento_versoes
  add column if not exists decisao        text,        -- null = pendente
  add column if not exists decisao_motivo text,        -- motivo (recusa / pedido de alteração)
  add column if not exists decidido_por   uuid references public.profiles(id) on delete set null,
  add column if not exists decidido_em    timestamptz;
alter table public.orcamento_versoes drop constraint if exists orcamento_versoes_decisao_chk;
alter table public.orcamento_versoes
  add constraint orcamento_versoes_decisao_chk
  check (decisao is null or decisao in ('aprovado', 'alteracao_pedida', 'recusado'));

-- ===================== (2) guard de orcamento_versoes (base 0060 + exceção da decisão) =====================
create or replace function public.orcamento_versoes_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.projetos pj
                   where pj.id = new.projeto_id and pj.tenant_id = new.tenant_id) then
      raise exception 'tenant/projeto incoerentes' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo_projeto(new.projeto_id) then
      raise exception 'apenas arquiteto cria orcamento' using errcode = '42501';
    end if;
    return new;
  end if;
  -- UPDATE: identidade IMUTÁVEL
  if new.id is distinct from old.id
     or new.tenant_id is distinct from old.tenant_id
     or new.projeto_id is distinct from old.projeto_id
     or new.numero is distinct from old.numero
     or new.created_at is distinct from old.created_at
     or new.created_by is distinct from old.created_by then
    raise exception 'identidade/numero da versao sao imutaveis' using errcode = '42501';
  end if;
  -- EXCEÇÃO: o CLIENTE registra a DECISÃO numa versão ENVIADA e ainda PENDENTE. Só as colunas de
  -- decisão mudam (allowlist via to_jsonb); a RLS bloqueia o acesso direto → só a RPC definer chega.
  if not public.is_arquiteto_ativo_projeto(old.projeto_id) then
    if old.enviado
       and old.decisao is null
       and new.decisao in ('aprovado', 'alteracao_pedida', 'recusado')
       and new.decidido_por = (select auth.uid())
       and public.meu_papel_projeto(old.projeto_id) = 'cliente'
       and (to_jsonb(new) - 'decisao' - 'decisao_motivo' - 'decidido_por' - 'decidido_em'
                          - 'updated_at')
         = (to_jsonb(old) - 'decisao' - 'decisao_motivo' - 'decidido_por' - 'decidido_em'
                          - 'updated_at')
    then
      return new;  -- decisão legítima do cliente
    end if;
    raise exception 'apenas arquiteto altera o orcamento' using errcode = '42501';
  end if;
  -- (arquiteto) versão CONGELADA é só-leitura (exceto a própria transição false→true)
  if old.congelado then
    raise exception 'versao congelada e somente leitura' using errcode = '42501';
  end if;
  if new.congelado is distinct from old.congelado and new.congelado = false then
    raise exception 'nao e possivel descongelar uma versao' using errcode = '42501';
  end if;
  -- a DECISÃO é verbo do cliente: o arquiteto não a define
  if new.decisao is distinct from old.decisao then
    raise exception 'a decisao da proposta e do cliente' using errcode = '42501';
  end if;
  return new;
end;
$$;
alter function public.orcamento_versoes_guard() owner to postgres;
-- (trigger trg_orcamento_versoes_guard já existe do 0060; replace na função basta.)

-- ===================== (3) guard de oportunidades (base 0059 + exceção do avanço p/ ganho) =====================
create or replace function public.oportunidades_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if new.tenant_id is distinct from (select auth.uid()) then
      raise exception 'oportunidade pertence a outro tenant' using errcode = '42501';
    end if;
    if new.obra_id is not null and not exists (
         select 1 from public.obras o where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'obra vinculada nao pertence ao tenant da oportunidade' using errcode = '42501';
    end if;
    if new.projeto_id is not null and not exists (
         select 1 from public.projetos p where p.id = new.projeto_id and p.tenant_id = new.tenant_id) then
      raise exception 'projeto vinculado nao pertence ao tenant da oportunidade' using errcode = '42501';
    end if;
    return new;
  end if;
  -- UPDATE: identidade IMUTÁVEL
  if new.id is distinct from old.id
     or new.tenant_id is distinct from old.tenant_id
     or new.created_by is distinct from old.created_by
     or new.created_at is distinct from old.created_at then
    raise exception 'identidade da oportunidade e imutavel' using errcode = '42501';
  end if;
  if old.tenant_id is distinct from (select auth.uid()) then
    -- EXCEÇÃO: o CLIENTE do projeto vinculado avança o funil p/ 'ganho' ao aprovar a proposta. Só a
    -- coluna 'etapa' (→ ganho) muda; a RLS bloqueia o acesso direto → só a RPC definer chega aqui.
    if old.projeto_id is not null
       and new.etapa = 'ganho'
       and public.meu_papel_projeto(old.projeto_id) = 'cliente'
       and (to_jsonb(new) - 'etapa' - 'updated_at') = (to_jsonb(old) - 'etapa' - 'updated_at')
    then
      return new;  -- avanço legítimo pelo cliente
    end if;
    raise exception 'apenas o dono altera a oportunidade' using errcode = '42501';
  end if;
  -- vincular/trocar obra: a obra NOVA tem de ser do MESMO tenant (anti cross-tenant)
  if new.obra_id is not null and new.obra_id is distinct from old.obra_id and not exists (
       select 1 from public.obras o where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
    raise exception 'obra vinculada nao pertence ao tenant da oportunidade' using errcode = '42501';
  end if;
  -- vincular/trocar projeto: idem
  if new.projeto_id is not null and new.projeto_id is distinct from old.projeto_id and not exists (
       select 1 from public.projetos p where p.id = new.projeto_id and p.tenant_id = new.tenant_id) then
    raise exception 'projeto vinculado nao pertence ao tenant da oportunidade' using errcode = '42501';
  end if;
  return new;
end;
$$;
alter function public.oportunidades_guard() owner to postgres;
-- (trigger trg_oportunidades_guard já existe do 0058; replace na função basta.)

-- ===================== (4) RPC: cliente decide a proposta =====================
-- Valida (cliente do projeto + versão enviada + pendente), grava a decisão, avança a oportunidade
-- vinculada p/ 'ganho' (se aprovado), audita (projeto) e devolve o contato do arquiteto p/ a camada
-- de e-mail. Idempotente-defensiva: 'proposta ja decidida' (P0001) se decisão != null.
-- Retorna arquiteto_id (NÃO o e-mail): a função é grant a 'authenticated' → o cliente pode chamá-la
-- direto via PostgREST e leria o retorno; PII do arquiteto fica fora daqui (alinha à regra B2 do
-- list_membros). O backend resolve o e-mail server-side a partir do id (profiles).
create or replace function public.decidir_orcamento_versao(
  p_projeto uuid, p_versao uuid, p_decisao text, p_motivo text)
returns table (
  numero int, decisao text, arquiteto_id uuid, projeto_nome text,
  oportunidade_id uuid, oportunidade_seq bigint, oportunidade_nome text)
language plpgsql security definer set search_path = '' as $$
declare
  v_uid       uuid := (select auth.uid());
  v_enviado   boolean;
  v_congelado boolean;
  v_decisao   text;
  v_seq       bigint;
  v_motivo    text;
  v_op_id     uuid;
begin
  if v_uid is null then
    raise exception 'sem usuario autenticado' using errcode = '28000';
  end if;
  if p_decisao not in ('aprovado', 'alteracao_pedida', 'recusado') then
    raise exception 'decisao invalida' using errcode = '22023';
  end if;
  if public.meu_papel_projeto(p_projeto) is distinct from 'cliente' then
    raise exception 'apenas o cliente decide a proposta' using errcode = '42501';
  end if;
  v_motivo := nullif(btrim(coalesce(p_motivo, '')), '');
  if p_decisao in ('recusado', 'alteracao_pedida') and v_motivo is null then
    raise exception 'informe o motivo' using errcode = '22023';
  end if;
  if p_decisao = 'aprovado' then
    v_motivo := null;
  end if;

  -- trava a versão; tem de ser do projeto, ENVIADA, não SUPERADA (congelada) e ainda pendente
  select v.enviado, v.congelado, v.decisao, v.numero, v.seq_humano
    into v_enviado, v_congelado, v_decisao, numero, v_seq
  from public.orcamento_versoes v
  where v.id = p_versao and v.projeto_id = p_projeto
  for update;
  if numero is null then
    raise exception 'proposta nao encontrada' using errcode = 'P0002';
  end if;
  if not v_enviado then
    raise exception 'proposta nao enviada' using errcode = '42501';
  end if;
  if v_congelado then
    -- versão superada por uma nova revisão: o cliente decide a vigente, não a antiga
    raise exception 'proposta superada' using errcode = '42501';
  end if;
  if v_decisao is not null then
    raise exception 'proposta ja decidida' using errcode = 'P0001';
  end if;

  update public.orcamento_versoes
    set decisao = p_decisao, decisao_motivo = v_motivo, decidido_por = v_uid, decidido_em = now()
  where id = p_versao;

  select pj.nome into projeto_nome from public.projetos pj where pj.id = p_projeto;

  -- arquiteto (dono do projeto) — devolve só o ID; o backend resolve o e-mail (não vazar PII aqui).
  -- order by created_at: determinístico (o arquiteto fundador) se houver mais de um ativo.
  select pm.profile_id into arquiteto_id
  from public.projeto_membros pm
  where pm.projeto_id = p_projeto and pm.papel = 'arquiteto' and pm.estado = 'ativo'
  order by pm.created_at
  limit 1;

  -- aprovado: avança a oportunidade vinculada p/ 'ganho' (se houver e não terminal)
  if p_decisao = 'aprovado' then
    select o.id, o.seq_humano, o.nome
      into v_op_id, oportunidade_seq, oportunidade_nome
    from public.oportunidades o
    where o.projeto_id = p_projeto and o.etapa not in ('ganho', 'perdido')
    for update;
    if v_op_id is not null then
      update public.oportunidades set etapa = 'ganho' where id = v_op_id;
    end if;
  end if;
  oportunidade_id := v_op_id;

  -- audit (evento de PROJETO; o cliente é membro → cria_audit_log 11-arg aceita)
  perform public.cria_audit_log(
    null, null, null,
    case p_decisao when 'aprovado' then 'orcamento.aprovado'
                   when 'recusado' then 'orcamento.recusado'
                   else 'orcamento.alteracao_pedida' end,
    'orcamento_versao', p_versao,
    jsonb_build_object('decisao', p_decisao, 'motivo', v_motivo),
    'Orçamento R' || numero, v_seq, null, p_projeto);
  if v_op_id is not null then
    perform public.cria_audit_log(
      null, null, null, 'oportunidade.ganho', 'oportunidade', v_op_id,
      jsonb_build_object('por', 'aceite_orcamento'), oportunidade_nome, oportunidade_seq, null,
      p_projeto);
  end if;

  decisao := p_decisao;
  return next;
end;
$$;
alter function public.decidir_orcamento_versao(uuid, uuid, text, text) owner to postgres;
revoke all on function public.decidir_orcamento_versao(uuid, uuid, text, text) from public, anon;
grant execute on function public.decidir_orcamento_versao(uuid, uuid, text, text) to authenticated;

-- ===================== (5) proposta expõe a decisão (recria as funções do 0078) =====================
-- DROP antes do CREATE: o 0078 criou estas funções com um RETURNS TABLE menor; adicionar colunas de
-- decisão muda o tipo de retorno e o Postgres recusa CREATE OR REPLACE (42P13). DROP+CREATE também
-- deixa a 0079 idempotente (re-rodável após falha parcial). Os grants são reaplicados logo abaixo.
drop function if exists public.orcamento_proposta_resumos(uuid);
create or replace function public.orcamento_proposta_resumos(p_projeto uuid)
returns table (id uuid, numero int, data date, validade date, enviado_em timestamptz,
               decisao text, decidido_em timestamptz, preco_final numeric)
language plpgsql stable security definer set search_path = '' as $$
declare v_arq boolean;
begin
  if not (p_projeto in (select public.current_projeto_ids())) then
    return;
  end if;
  v_arq := public.is_arquiteto_ativo_projeto(p_projeto);  -- arquiteto vê não-enviadas (preview)
  return query
    select v.id, v.numero, v.data, v.validade, v.enviado_em, v.decisao, v.decidido_em,
           ( coalesce(b.base_mo, 0)         * (1 + v.maj_mo / 100)
           + coalesce(b.base_material, 0)   * (1 + v.maj_material / 100)
           + coalesce(b.base_equipamento, 0)* (1 + v.maj_equipamento / 100) )
           * (1 + v.bdi / 100) * (1 + v.imposto / 100) as preco_final
    from public.orcamento_versoes v
    left join lateral (
      select sum(i.valor_mo * i.m)          as base_mo,
             sum(i.valor_material * i.m)    as base_material,
             sum(i.valor_equipamento * i.m) as base_equipamento
      from (
        select valor_mo, valor_material, valor_equipamento,
               case when quantidade > 0 then quantidade else 1 end as m
        from public.orcamento_itens where versao_id = v.id
      ) i
    ) b on true
    -- cliente vê ENVIADAS não superadas + as que ele já DECIDIU (histórico do aceite, mesmo
    -- congeladas); o arquiteto vê todas (preview).
    where v.projeto_id = p_projeto
          and (v_arq or (v.enviado and (not v.congelado or v.decisao is not null)))
    order by v.numero;
end;
$$;
alter function public.orcamento_proposta_resumos(uuid) owner to postgres;
revoke all on function public.orcamento_proposta_resumos(uuid) from public, anon;
grant execute on function public.orcamento_proposta_resumos(uuid) to authenticated;

drop function if exists public.orcamento_proposta_versao(uuid, uuid);
create or replace function public.orcamento_proposta_versao(p_projeto uuid, p_versao uuid)
returns table (id uuid, numero int, data date, validade date, enviado_em timestamptz,
               observacoes text, decisao text, decisao_motivo text, decidido_em timestamptz,
               preco_final numeric)
language plpgsql stable security definer set search_path = '' as $$
declare v_arq boolean;
begin
  if not (p_projeto in (select public.current_projeto_ids())) then
    return;
  end if;
  v_arq := public.is_arquiteto_ativo_projeto(p_projeto);  -- arquiteto vê não-enviadas (preview)
  return query
    select v.id, v.numero, v.data, v.validade, v.enviado_em, v.observacoes,
           v.decisao, v.decisao_motivo, v.decidido_em,
           ( coalesce(b.base_mo, 0)         * (1 + v.maj_mo / 100)
           + coalesce(b.base_material, 0)   * (1 + v.maj_material / 100)
           + coalesce(b.base_equipamento, 0)* (1 + v.maj_equipamento / 100) )
           * (1 + v.bdi / 100) * (1 + v.imposto / 100) as preco_final
    from public.orcamento_versoes v
    left join lateral (
      select sum(i.valor_mo * i.m)          as base_mo,
             sum(i.valor_material * i.m)    as base_material,
             sum(i.valor_equipamento * i.m) as base_equipamento
      from (
        select valor_mo, valor_material, valor_equipamento,
               case when quantidade > 0 then quantidade else 1 end as m
        from public.orcamento_itens where versao_id = v.id
      ) i
    ) b on true
    where v.id = p_versao and v.projeto_id = p_projeto
          and (v_arq or (v.enviado and (not v.congelado or v.decisao is not null)));
end;
$$;
alter function public.orcamento_proposta_versao(uuid, uuid) owner to postgres;
revoke all on function public.orcamento_proposta_versao(uuid, uuid) from public, anon;
grant execute on function public.orcamento_proposta_versao(uuid, uuid) to authenticated;

-- itens: MESMO predicado de visibilidade das funções acima (estava só no 0078 com o filtro antigo
-- 'v.enviado or arquiteto' → cliente alcançaria linhas de versão superada via PostgREST direto).
drop function if exists public.orcamento_proposta_itens(uuid, uuid);
create or replace function public.orcamento_proposta_itens(p_projeto uuid, p_versao uuid)
returns table (etapa text, ordem_etapa int, descricao text, ordem int, ambiente text,
               unidade text, quantidade numeric, valor numeric)
language plpgsql stable security definer set search_path = '' as $$
declare
  v_maj_mo  numeric(6,3); v_maj_mat numeric(6,3); v_maj_eq numeric(6,3);
  v_bdi     numeric(6,3); v_imp     numeric(6,3);
  v_ok      boolean;
begin
  if not (p_projeto in (select public.current_projeto_ids())) then
    return;
  end if;
  -- versão deste projeto, visível ao chamador: arquiteto vê qualquer; cliente só enviada não
  -- superada OU já decidida (histórico).
  select true, v.maj_mo, v.maj_material, v.maj_equipamento, v.bdi, v.imposto
    into v_ok, v_maj_mo, v_maj_mat, v_maj_eq, v_bdi, v_imp
    from public.orcamento_versoes v
    where v.id = p_versao and v.projeto_id = p_projeto
          and (public.is_arquiteto_ativo_projeto(p_projeto)
               or (v.enviado and (not v.congelado or v.decisao is not null)));
  if not coalesce(v_ok, false) then
    return;
  end if;
  return query
    select i.etapa, i.ordem_etapa, i.descricao, i.ordem, i.ambiente, i.unidade, i.quantidade,
           ( i.valor_mo          * (1 + v_maj_mo  / 100)
           + i.valor_material    * (1 + v_maj_mat / 100)
           + i.valor_equipamento * (1 + v_maj_eq  / 100) )
           * (case when i.quantidade > 0 then i.quantidade else 1 end)
           * (1 + v_bdi / 100) * (1 + v_imp / 100) as valor
    from public.orcamento_itens i
    where i.versao_id = p_versao
    order by i.ordem_etapa, i.ordem, i.descricao;
end;
$$;
alter function public.orcamento_proposta_itens(uuid, uuid) owner to postgres;
revoke all on function public.orcamento_proposta_itens(uuid, uuid) from public, anon;
grant execute on function public.orcamento_proposta_itens(uuid, uuid) to authenticated;
