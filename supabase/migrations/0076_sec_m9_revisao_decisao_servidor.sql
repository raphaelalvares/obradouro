-- 0076_sec_m9_revisao_decisao_servidor.sql  (SEGURANÇA — Fase 2, item M9 / MÉDIO)
--
-- BUG (red-report Fase 1, M9): no ramo CLIENTE do revisoes_guard (0040), a transição de status é
-- validada, mas `decidido_por`/`decidido_em` NÃO eram carimbados pelo servidor. Como a policy de
-- UPDATE de `revisoes` permite a qualquer membro ativo do projeto (`projeto_id in
-- current_projeto_ids()`) e a RLS é a única fronteira, um CLIENTE podia, via PostgREST direto, decidir
-- a revisão carimbando `decidido_por` = id de OUTRA pessoa (ex.: o arquiteto) e um `decidido_em`
-- falso → falsifica "quem/quando decidiu" no registro formal de decisão.
-- (Pela API o serviço decidir() já seta decidido_por=auth.uid()/decidido_em=now(); o furo é só o
-- caminho direto.)
--
-- CORREÇÃO: o guard passa a CARIMBAR `decidido_por := auth.uid()` e `decidido_em := now()` no ramo
-- cliente (sobrescreve o que vier do chamador). Para o fluxo legítimo é no-op (a API já manda os
-- mesmos valores); para o Path B, neutraliza a forja. O ramo arquiteto continua bloqueando qualquer
-- mudança de status/motivo/decidido_* (a decisão é verbo do cliente).
--
-- Recria a função revisoes_guard IDÊNTICA à 0040 + as 2 linhas do carimbo. Mantém SECURITY DEFINER +
-- search_path=''. Aplicar como postgres, DEPOIS da 0040. DEV antes de PROD.
--
-- VERIFICAR após aplicar:
--   -- decisão pela API segue funcionando (cliente aprova/recusa/pede alteração);
--   -- via PostgREST direto, um UPDATE de revisoes com decidido_por arbitrário é IGNORADO
--   --   (o valor gravado é sempre auth.uid()); o arquiteto continua sem poder decidir.

begin;

create or replace function public.revisoes_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.projetos pj
                   where pj.id = new.projeto_id and pj.tenant_id = new.tenant_id) then
      raise exception 'tenant/projeto incoerentes' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo_projeto(new.projeto_id) then
      raise exception 'apenas arquiteto cria revisao' using errcode = '42501';
    end if;
    return new;
  end if;
  -- UPDATE: identidade/numero IMUTÁVEIS p/ todos
  if new.id is distinct from old.id
     or new.tenant_id is distinct from old.tenant_id
     or new.projeto_id is distinct from old.projeto_id
     or new.numero is distinct from old.numero
     or new.created_at is distinct from old.created_at
     or new.created_by is distinct from old.created_by then
    raise exception 'identidade/numero da revisao sao imutaveis' using errcode = '42501';
  end if;
  v_papel := public.meu_papel_projeto(old.projeto_id);
  if v_papel = 'arquiteto' then
    -- arquiteto edita só titulo; a DECISÃO é verbo do cliente
    if new.status is distinct from old.status
       or new.motivo is distinct from old.motivo
       or new.decidido_por is distinct from old.decidido_por
       or new.decidido_em is distinct from old.decidido_em then
      raise exception 'a decisao da revisao e do cliente' using errcode = '42501';
    end if;
    return new;
  elsif v_papel = 'cliente' then
    if old.status <> 'pendente' then
      raise exception 'revisao ja decidida' using errcode = '42501';
    end if;
    if new.titulo is distinct from old.titulo then
      raise exception 'cliente nao edita o titulo da revisao' using errcode = '42501';
    end if;
    if new.status not in ('aprovado', 'alteracao_pedida', 'recusado') then
      raise exception 'transicao de status invalida' using errcode = '42501';
    end if;
    -- M9: a decisão é SEMPRE carimbada pelo servidor (cliente não forja quem/quando decidiu, nem
    -- via PostgREST direto). decidido_por = o ator; decidido_em = agora.
    new.decidido_por := (select auth.uid());
    new.decidido_em := now();
    return new;
  else
    raise exception 'sem permissao na revisao' using errcode = '42501';
  end if;
end;
$$;
alter function public.revisoes_guard() owner to postgres;

drop trigger if exists trg_revisoes_guard on public.revisoes;
create trigger trg_revisoes_guard
  before insert or update on public.revisoes
  for each row execute function public.revisoes_guard();

commit;
