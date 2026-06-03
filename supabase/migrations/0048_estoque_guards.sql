-- 0048_estoque_guards.sql  (Fase 6 — CORE: camada 2, regra fina que a RLS nao expressa)
-- Espelha checklist_itens_guard (0025). Disparam ANTES dos triggers de seq ('..._guard' < '..._seq')
-- => coerencia de tenant_id validada antes de alocar seq. Owner postgres; SECURITY DEFINER p/ ler
-- obras/obra_membros. Os campos vindos do XML sao a VERDADE da nota e ficam IMUTAVEIS (so data_chegada
-- na nota e nome_editado/conferencia no item podem variar).

-- (A) NOTAS: create/delete SO arquiteto; no UPDATE so `data_chegada` muda (resto imutavel).
create or replace function public.notas_fiscais_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo(new.obra_id) then
      raise exception 'apenas arquiteto pode criar nota' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    if not public.is_arquiteto_ativo(old.obra_id) then
      raise exception 'apenas arquiteto pode alterar nota' using errcode = '42501';
    end if;
    -- so data_chegada (e updated_at, setado depois por outro trigger) podem mudar
    if new.id            is distinct from old.id
       or new.obra_id       is distinct from old.obra_id
       or new.tenant_id     is distinct from old.tenant_id
       or new.chave_acesso  is distinct from old.chave_acesso
       or new.numero        is distinct from old.numero
       or new.serie         is distinct from old.serie
       or new.emitente_nome is distinct from old.emitente_nome
       or new.emitente_cnpj is distinct from old.emitente_cnpj
       or new.data_emissao  is distinct from old.data_emissao
       or new.valor_total   is distinct from old.valor_total
       or new.xml           is distinct from old.xml
       or new.seq_humano    is distinct from old.seq_humano
       or new.created_by    is distinct from old.created_by
       or new.created_at    is distinct from old.created_at then
      raise exception 'nota e imutavel exceto data de chegada' using errcode = '42501';
    end if;
    return new;
  end if;

  -- DELETE
  if not public.is_arquiteto_ativo(old.obra_id) then
    raise exception 'apenas arquiteto pode remover nota' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.notas_fiscais_guard() owner to postgres;
drop trigger if exists trg_notas_fiscais_guard on public.notas_fiscais;
create trigger trg_notas_fiscais_guard
  before insert or update or delete on public.notas_fiscais
  for each row execute function public.notas_fiscais_guard();

-- (B) ITENS: arquiteto = nome_editado + conferencia; prestador = SO conferencia; cliente/nao-membro =
-- nada. Campos do XML (codigo/descricao/ncm/unidade/quantidade_nota/valores/ordem) + identidade sao
-- IMUTAVEIS p/ TODOS. INSERT/DELETE so arquiteto. Allowlist do prestador: qualquer coluna nova futura
-- fica travada p/ prestador por padrao.
create or replace function public.nota_itens_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    if not exists (select 1 from public.notas_fiscais n
                   where n.id = new.nota_id and n.obra_id = new.obra_id) then
      raise exception 'nota nao pertence a obra do item' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo(new.obra_id) then
      raise exception 'apenas arquiteto pode criar item de nota' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    -- identidade + dados do XML nunca mudam por UPDATE (vale ate p/ arquiteto)
    if new.id is distinct from old.id
       or new.nota_id         is distinct from old.nota_id
       or new.obra_id         is distinct from old.obra_id
       or new.tenant_id       is distinct from old.tenant_id
       or new.codigo          is distinct from old.codigo
       or new.descricao       is distinct from old.descricao
       or new.ncm             is distinct from old.ncm
       or new.unidade         is distinct from old.unidade
       or new.quantidade_nota is distinct from old.quantidade_nota
       or new.valor_unitario  is distinct from old.valor_unitario
       or new.valor_total     is distinct from old.valor_total
       or new.ordem           is distinct from old.ordem
       or new.created_at       is distinct from old.created_at then
      raise exception 'dados do item (vindos do XML) sao imutaveis' using errcode = '42501';
    end if;

    v_papel := public.meu_papel_obra(old.obra_id);
    if v_papel = 'arquiteto' then
      return new;                                     -- nome_editado + conferencia livres
    elsif v_papel = 'prestador' then
      -- ALLOWLIST: so a conferencia muda; nome_editado e do arquiteto.
      if new.nome_editado is distinct from old.nome_editado then
        raise exception 'prestador so pode conferir a quantidade' using errcode = '42501';
      end if;
      return new;
    else
      raise exception 'sem permissao para alterar item de nota' using errcode = '42501';
    end if;
  end if;

  -- DELETE: so arquiteto
  if not public.is_arquiteto_ativo(old.obra_id) then
    raise exception 'apenas arquiteto pode remover item de nota' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.nota_itens_guard() owner to postgres;
drop trigger if exists trg_nota_itens_guard on public.nota_itens;
create trigger trg_nota_itens_guard
  before insert or update or delete on public.nota_itens
  for each row execute function public.nota_itens_guard();
