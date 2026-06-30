-- 0098_revisao_opcoes_layout.sql  (2ª rodada do portal — FEATURE A: Layouts 1-de-3)
--
-- Uma revisão pode trazer OPÇÕES de layout (ex.: 3 propostas). Cada arquivo ganha `opcao` (1..9,
-- null = arquivo sem opção / fluxo antigo). Se a revisão tem arquivos com `opcao` não-nula, ela é
-- uma revisão "de opções" → o cliente ESCOLHE uma (em vez de só "aprovar"); a opção escolhida fica
-- em `revisoes.opcao_escolhida`. Sem arquivos com opção = fluxo atual intacto (backward-compat).
--
-- Recria `revisoes_guard` IDÊNTICA à 0076 (preserva o carimbo M9: decidido_por/decidido_em sempre
-- pelo servidor) + permite o cliente gravar `opcao_escolhida` ao decidir, com integridade:
--   • a opção escolhida tem de existir entre os arquivos da revisão;
--   • aprovar uma revisão COM opções exige escolher uma (defesa em profundidade do path PostgREST);
--   • o arquiteto continua sem poder mexer na decisão (inclui opcao_escolhida).
--
-- `revisao_arquivos.opcao` é setada no INSERT (a tabela é imutável; revisao_arquivos_guard 0040 não
-- toca a coluna nova → INSERT segue ok). Aplicar como postgres, DEPOIS da 0076. DEV antes de PROD.

begin;

-- ===================== colunas =====================
alter table public.revisao_arquivos
  add column if not exists opcao smallint
  check (opcao is null or opcao between 1 and 9);

alter table public.revisoes
  add column if not exists opcao_escolhida smallint
  check (opcao_escolhida is null or opcao_escolhida between 1 and 9);

-- ===================== guard (0076 + opção) =====================
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
    -- arquiteto edita só titulo; a DECISÃO (inclui a opção escolhida) é verbo do cliente
    if new.status is distinct from old.status
       or new.motivo is distinct from old.motivo
       or new.opcao_escolhida is distinct from old.opcao_escolhida
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
    -- INTEGRIDADE das opções (também fecha o path PostgREST direto):
    --  • a opção escolhida tem de existir entre os arquivos desta revisão;
    --  • aprovar uma revisão COM opções exige escolher uma; opção só faz sentido ao aprovar.
    if new.opcao_escolhida is not null then
      if new.status <> 'aprovado' then
        raise exception 'opcao so na aprovacao' using errcode = '23514';
      end if;
      if not exists (select 1 from public.revisao_arquivos ra
                     where ra.revisao_id = new.id and ra.opcao = new.opcao_escolhida) then
        raise exception 'opcao escolhida nao existe entre os arquivos' using errcode = '23514';
      end if;
    elsif new.status = 'aprovado' and exists (
            select 1 from public.revisao_arquivos ra
            where ra.revisao_id = new.id and ra.opcao is not null) then
      raise exception 'aprovacao de layout exige escolher uma opcao' using errcode = '23514';
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
