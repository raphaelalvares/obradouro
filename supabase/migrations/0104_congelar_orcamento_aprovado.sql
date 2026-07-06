-- 0104_congelar_orcamento_aprovado.sql  (proposta APROVADA vira só-leitura)
--
-- Bug de integridade (auditoria do fluxo do cliente): depois que o cliente APROVA a proposta
-- (decidir_orcamento_versao grava decisao='aprovado' MAS não congela a versão — 0079), a versão
-- aprovada continua sendo a única editável do projeto (congelado=false). Os guards de edição olhavam
-- só `congelado`, então o arquiteto ainda podia mudar itens/percentuais DEPOIS do aceite — e como o
-- preço da proposta é recomputado AO VIVO pelas funções de proposta (0078/0079), o "preço aprovado"
-- que o cliente vê mudava retroativamente. Contrato aceito não pode mudar sem novo aceite.
--
-- Correção: a versão com decisao='aprovado' passa a ser SÓ-LEITURA, igual a `congelado`. A ÚNICA
-- escrita permitida nela é a transição congelado false→true feita por criar_orcamento_versao (0060)
-- ao clonar uma NOVA versão — o caminho correto para revisar depois do aceite. Com os itens/params
-- imutáveis, o recomputo ao vivo das funções de proposta fica estável (não há mais reescrita
-- retroativa) — sem precisar de snapshot de preço.
--
-- Espelha em SQL (2ª camada) o mesmo gate que o backend passa a aplicar (orcamentos.py). A camada da
-- API é a 1ª barreira; estes guards fecham o acesso direto via PostgREST.
--
-- Depende de: 0060 (guards base), 0079 (guard + exceção da decisão do cliente). Aplicar como
-- postgres, após 0103. Idempotente (create or replace).

begin;

-- ===================== orcamento_versoes_guard: + APROVADA é só-leitura =====================
-- Base = 0079 (que já tem a exceção da DECISÃO do cliente, mantida IGUAL). Acrescenta, no ramo do
-- ARQUITETO, a trava de "aprovada é imutável" — deixando passar só a transição p/ congelada (clone).
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
  -- EXCEÇÃO (0079): o CLIENTE registra a DECISÃO numa versão ENVIADA e ainda PENDENTE.
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
  -- NOVO: proposta APROVADA é imutável — só passa a transição p/ CONGELADA (clone de nova versão via
  -- criar_orcamento_versao). Qualquer outra mudança (itens são barrados no itens_guard; aqui, params)
  -- é recusada: o contrato aceito não muda sem novo aceite.
  if old.decisao = 'aprovado'
     and (to_jsonb(new) - 'congelado' - 'updated_at')
       is distinct from (to_jsonb(old) - 'congelado' - 'updated_at') then
    raise exception 'proposta aprovada e somente leitura — crie uma nova versao para editar'
      using errcode = '42501';
  end if;
  -- a DECISÃO é verbo do cliente: o arquiteto não a define
  if new.decisao is distinct from old.decisao then
    raise exception 'a decisao da proposta e do cliente' using errcode = '42501';
  end if;
  return new;
end;
$$;
alter function public.orcamento_versoes_guard() owner to postgres;

-- ===================== orcamento_itens_guard: versão-pai não pode estar APROVADA =====================
-- Base = 0060 + o predicado da versão-pai passa a exigir também decisao != 'aprovado' (além de
-- congelado=false). Itens de proposta aprovada ficam imutáveis; a nova versão (clone) nasce
-- decisao=null e volta a aceitar itens.
create or replace function public.orcamento_itens_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  v_versao uuid := coalesce(new.versao_id, old.versao_id);
  v_projeto uuid := coalesce(new.projeto_id, old.projeto_id);
begin
  if not public.is_arquiteto_ativo_projeto(v_projeto) then
    raise exception 'apenas arquiteto edita o orcamento' using errcode = '42501';
  end if;
  -- versão-pai: existe, mesmo tenant/projeto, EDITÁVEL (não-congelada) e NÃO aprovada
  if not exists (
       select 1 from public.orcamento_versoes v
       where v.id = v_versao and v.projeto_id = v_projeto
         and v.congelado = false and v.decisao is distinct from 'aprovado') then
    raise exception 'versao inexistente, congelada ou aprovada' using errcode = '42501';
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  if tg_op = 'UPDATE'
     and (new.id is distinct from old.id
          or new.versao_id is distinct from old.versao_id
          or new.tenant_id is distinct from old.tenant_id
          or new.projeto_id is distinct from old.projeto_id) then
    raise exception 'identidade do item e imutavel' using errcode = '42501';
  end if;
  return new;
end;
$$;
alter function public.orcamento_itens_guard() owner to postgres;

commit;
