-- 0056_cronograma_datas.sql
-- Cronograma com datas: data_inicio/data_fim nas TAREFAS (checklist_itens). A ETAPA deriva as datas
-- dos seus itens (min/max, calculado na leitura); se a etapa NÃO tem item, usa as datas próprias
-- (colunas abaixo, preenchíveis direto). A OBRA guarda início/fim (o "cronograma macro" parte daí).
-- Datas sem hora (date), dias corridos. Aplicar como postgres. DEV antes de PROD.

alter table public.checklist_itens
  add column if not exists data_inicio date,
  add column if not exists data_fim    date;

alter table public.etapas
  add column if not exists data_inicio date,   -- usadas só quando a etapa não tem itens
  add column if not exists data_fim    date;

alter table public.obras
  add column if not exists data_inicio date,
  add column if not exists data_fim    date;

-- Guard do item: o prestador NÃO pode mexer no cronograma (datas). Acrescenta data_inicio/data_fim
-- à allowlist negada do prestador (só estado/conclusão podem variar p/ ele). Recria a função (0025).
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
    if not public.is_arquiteto_ativo(new.obra_id) then
      raise exception 'apenas arquiteto pode criar item' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    if new.id is distinct from old.id
       or new.tenant_id is distinct from old.tenant_id
       or new.obra_id  is distinct from old.obra_id
       or new.etapa_id is distinct from old.etapa_id
       or new.created_at is distinct from old.created_at then
      raise exception 'identidade/escopo do item sao imutaveis' using errcode = '42501';
    end if;

    v_papel := public.meu_papel_obra(old.obra_id);
    if v_papel = 'arquiteto' then
      return new;
    elsif v_papel = 'prestador' then
      -- ALLOWLIST: prestador só muda estado/conclusão. nome/ordem/seq/DATAS são imutáveis p/ ele.
      if new.nome        is distinct from old.nome
         or new.nome_norm   is distinct from old.nome_norm
         or new.ordem       is distinct from old.ordem
         or new.seq_humano  is distinct from old.seq_humano
         or new.data_inicio is distinct from old.data_inicio
         or new.data_fim    is distinct from old.data_fim then
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
-- trigger trg_itens_guard (0025) já aponta p/ esta função; não recriar.
