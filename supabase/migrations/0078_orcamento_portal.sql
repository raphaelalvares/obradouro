-- 0078_orcamento_portal.sql  (Orçamento: cliente vê a PROPOSTA no portal — SEM vazar margem)
--
-- REGRA: o cliente (membro não-arquiteto do projeto) só pode ver versões ENVIADAS e SÓ na visão de
-- VENDA (preço por linha = custo majorado × BDI × imposto). Custo cru por balde, majoração, BDI e
-- imposto NUNCA podem sair p/ não-arquiteto.
--
-- POR QUE NÃO ABRIR A RLS DAS TABELAS-BASE: no Supabase a role `authenticated` tem grant em TODA
-- tabela do schema public (ver 0075); a RLS é a ÚNICA fronteira e é por LINHA, não por coluna. Abrir
-- SELECT de orcamento_versoes/orcamento_itens ao cliente entregaria a LINHA INTEIRA (valor_* crus,
-- maj_*, bdi, imposto) via PostgREST direto (GET /rest/v1/...). Por isso as tabelas-base seguem
-- ARQUITETO-ONLY (políticas do 0060 intactas) e o portal é servido por funções SECURITY DEFINER que
-- retornam SÓ a visão de venda — seguras de expor a `authenticated` (padrão de central()/0036).
--
-- FÓRMULA (espelha services/orcamentos.py — _totais/_venda_item, FONTE da verdade em Python):
--   m (mult) = case when quantidade > 0 then quantidade else 1 end   (verba = ×1)
--   preço de venda por linha = (Σ_balde valor_balde × (1+maj_balde/100)) × m × (1+bdi/100) × (1+imp/100)
--   preço da versão        = Σ linhas  (a fórmula é linear nos itens → bate com totais.preco_final)
-- Mantida em SQL como em public.central()/0060 (mesma duplicação consciente, mesmo risco).
--
-- Depende de: 0060 (tabelas/políticas), 0036 (current_projeto_ids). Aplicar como postgres, após 0077.

-- ===================== resumo das propostas (versões ENVIADAS) =====================
create or replace function public.orcamento_proposta_resumos(p_projeto uuid)
returns table (id uuid, numero int, data date, validade date, enviado_em timestamptz,
               preco_final numeric)
language plpgsql stable security definer set search_path = '' as $$
begin
  -- membro ATIVO do projeto (arquiteto OU cliente)? senão devolve vazio (sem oráculo).
  if not (p_projeto in (select public.current_projeto_ids())) then
    return;
  end if;
  return query
    select v.id, v.numero, v.data, v.validade, v.enviado_em,
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
    where v.projeto_id = p_projeto and v.enviado
    order by v.numero;
end;
$$;
alter function public.orcamento_proposta_resumos(uuid) owner to postgres;
revoke all on function public.orcamento_proposta_resumos(uuid) from public, anon;
grant execute on function public.orcamento_proposta_resumos(uuid) to authenticated;

-- ===================== cabeçalho de UMA proposta enviada =====================
create or replace function public.orcamento_proposta_versao(p_projeto uuid, p_versao uuid)
returns table (id uuid, numero int, data date, validade date, enviado_em timestamptz,
               observacoes text, preco_final numeric)
language plpgsql stable security definer set search_path = '' as $$
begin
  if not (p_projeto in (select public.current_projeto_ids())) then
    return;
  end if;
  return query
    select v.id, v.numero, v.data, v.validade, v.enviado_em, v.observacoes,
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
    where v.id = p_versao and v.projeto_id = p_projeto and v.enviado;
end;
$$;
alter function public.orcamento_proposta_versao(uuid, uuid) owner to postgres;
revoke all on function public.orcamento_proposta_versao(uuid, uuid) from public, anon;
grant execute on function public.orcamento_proposta_versao(uuid, uuid) to authenticated;

-- ===================== linhas de uma proposta (preço de VENDA por linha) =====================
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
  -- a versão tem de ser deste projeto e estar ENVIADA
  select true, v.maj_mo, v.maj_material, v.maj_equipamento, v.bdi, v.imposto
    into v_ok, v_maj_mo, v_maj_mat, v_maj_eq, v_bdi, v_imp
    from public.orcamento_versoes v
    where v.id = p_versao and v.projeto_id = p_projeto and v.enviado;
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
