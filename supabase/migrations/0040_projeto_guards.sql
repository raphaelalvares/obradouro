-- 0040_projeto_guards.sql  (Fase 5 — CORE: camada 2 da regra fina por papel/coluna)
-- Espelham obra_membros_guard/checklist guards (0019/0025). Disparam ANTES do '..._seq' (nome
-- 'trg_<t>_guard' < 'trg_<t>_seq'). Owner postgres; SECURITY DEFINER. Achados adversariais embutidos:
--  - prestador NUNCA entra no projeto (INSERT em membros/codigos);
--  - anti-escalada de papel (espelha 0019);
--  - anti cross-tenant ao vincular obra (obra do MESMO tenant);
--  - lifecycle da revisão: imutáveis (numero/sinalizacao), arquiteto não decide, cliente só decide
--    UMA pendente, transição válida.

-- ===================== (A) PROJETOS =====================
create or replace function public.projetos_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if new.obra_id is not null and not exists (
         select 1 from public.obras o where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'obra vinculada nao pertence ao tenant do projeto' using errcode = '42501';
    end if;
    return new;
  end if;
  -- UPDATE
  if new.id is distinct from old.id
     or new.tenant_id is distinct from old.tenant_id
     or new.created_by is distinct from old.created_by
     or new.created_at is distinct from old.created_at then
    raise exception 'identidade do projeto e imutavel' using errcode = '42501';
  end if;
  if not public.is_arquiteto_ativo_projeto(old.id) then
    raise exception 'apenas arquiteto pode alterar o projeto' using errcode = '42501';
  end if;
  -- vincular/trocar obra: a obra NOVA tem de ser do MESMO tenant (anti cross-tenant)
  if new.obra_id is not null and new.obra_id is distinct from old.obra_id and not exists (
       select 1 from public.obras o where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
    raise exception 'obra vinculada nao pertence ao tenant do projeto' using errcode = '42501';
  end if;
  return new;
end;
$$;
alter function public.projetos_guard() owner to postgres;
drop trigger if exists trg_projetos_guard on public.projetos;
create trigger trg_projetos_guard
  before insert or update on public.projetos
  for each row execute function public.projetos_guard();

-- ===================== (B) PROJETO_MEMBROS (espelha 0019 + barra prestador) =====================
create or replace function public.projeto_membros_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if new.papel = 'prestador' then
      raise exception 'prestador nao participa de projeto' using errcode = '23514';
    end if;
    return new;
  end if;
  -- UPDATE: não-arquiteto não muda papel/profile/projeto (anti-escalada; o aceite só muda estado)
  if (new.papel is distinct from old.papel
      or new.profile_id is distinct from old.profile_id
      or new.projeto_id is distinct from old.projeto_id)
     and not public.is_arquiteto_ativo_projeto(old.projeto_id) then
    raise exception 'apenas arquiteto pode alterar papel/membro' using errcode = '42501';
  end if;
  if new.papel = 'prestador' then              -- nem o arquiteto promove a prestador no projeto
    raise exception 'prestador nao participa de projeto' using errcode = '23514';
  end if;
  return new;
end;
$$;
alter function public.projeto_membros_guard() owner to postgres;
drop trigger if exists trg_projeto_membros_guard on public.projeto_membros;
create trigger trg_projeto_membros_guard
  before insert or update on public.projeto_membros
  for each row execute function public.projeto_membros_guard();

-- ===================== (C) PROJETO_CODIGOS (sem prestador) =====================
create or replace function public.projeto_codigos_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if new.papel = 'prestador' then
    raise exception 'codigo de projeto nao concede prestador' using errcode = '23514';
  end if;
  return new;
end;
$$;
alter function public.projeto_codigos_guard() owner to postgres;
drop trigger if exists trg_projeto_codigos_guard on public.projeto_codigos;
create trigger trg_projeto_codigos_guard
  before insert or update on public.projeto_codigos
  for each row execute function public.projeto_codigos_guard();

-- ===================== (D) REVISOES (lifecycle por papel) =====================
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

-- ===================== (E) REVISAO_ARQUIVOS (imutável; só arquiteto) =====================
create or replace function public.revisao_arquivos_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.projetos pj
                   where pj.id = new.projeto_id and pj.tenant_id = new.tenant_id) then
      raise exception 'tenant/projeto incoerentes' using errcode = '23514';
    end if;
    if not exists (select 1 from public.revisoes r
                   where r.id = new.revisao_id and r.projeto_id = new.projeto_id) then
      raise exception 'revisao nao pertence ao projeto do arquivo' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo_projeto(new.projeto_id) then
      raise exception 'apenas arquiteto anexa arquivo de revisao' using errcode = '42501';
    end if;
    return new;
  end if;
  if tg_op = 'UPDATE' then
    raise exception 'arquivo de revisao e imutavel' using errcode = '42501';
  end if;
  -- DELETE
  if not public.is_arquiteto_ativo_projeto(old.projeto_id) then
    raise exception 'apenas arquiteto remove arquivo de revisao' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.revisao_arquivos_guard() owner to postgres;
drop trigger if exists trg_revisao_arquivos_guard on public.revisao_arquivos;
create trigger trg_revisao_arquivos_guard
  before insert or update or delete on public.revisao_arquivos
  for each row execute function public.revisao_arquivos_guard();

-- ===================== (F) MOODBOARD (só arquiteto cura; cliente só vê via RLS) =====================
create or replace function public.moodboard_secoes_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.projetos pj where pj.id = new.projeto_id and pj.tenant_id = new.tenant_id) then
      raise exception 'tenant/projeto incoerentes' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo_projeto(new.projeto_id) then
      raise exception 'apenas arquiteto edita o moodboard' using errcode = '42501';
    end if;
    return new;
  end if;
  if tg_op = 'UPDATE' then
    if new.id is distinct from old.id or new.tenant_id is distinct from old.tenant_id
       or new.projeto_id is distinct from old.projeto_id then
      raise exception 'identidade da secao e imutavel' using errcode = '42501';
    end if;
    if not public.is_arquiteto_ativo_projeto(old.projeto_id) then
      raise exception 'apenas arquiteto edita o moodboard' using errcode = '42501';
    end if;
    return new;
  end if;
  if not public.is_arquiteto_ativo_projeto(old.projeto_id) then
    raise exception 'apenas arquiteto edita o moodboard' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.moodboard_secoes_guard() owner to postgres;
drop trigger if exists trg_moodboard_secoes_guard on public.moodboard_secoes;
create trigger trg_moodboard_secoes_guard
  before insert or update or delete on public.moodboard_secoes
  for each row execute function public.moodboard_secoes_guard();

create or replace function public.moodboard_itens_guard()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.projetos pj where pj.id = new.projeto_id and pj.tenant_id = new.tenant_id) then
      raise exception 'tenant/projeto incoerentes' using errcode = '23514';
    end if;
    if new.secao_id is not null and not exists (
         select 1 from public.moodboard_secoes s where s.id = new.secao_id and s.projeto_id = new.projeto_id) then
      raise exception 'secao nao pertence ao projeto' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo_projeto(new.projeto_id) then
      raise exception 'apenas arquiteto edita o moodboard' using errcode = '42501';
    end if;
    return new;
  end if;
  if tg_op = 'UPDATE' then
    if new.id is distinct from old.id or new.tenant_id is distinct from old.tenant_id
       or new.projeto_id is distinct from old.projeto_id then
      raise exception 'identidade do item e imutavel' using errcode = '42501';
    end if;
    if new.secao_id is not null and new.secao_id is distinct from old.secao_id and not exists (
         select 1 from public.moodboard_secoes s where s.id = new.secao_id and s.projeto_id = new.projeto_id) then
      raise exception 'secao nao pertence ao projeto' using errcode = '23514';
    end if;
    if not public.is_arquiteto_ativo_projeto(old.projeto_id) then
      raise exception 'apenas arquiteto edita o moodboard' using errcode = '42501';
    end if;
    return new;
  end if;
  if not public.is_arquiteto_ativo_projeto(old.projeto_id) then
    raise exception 'apenas arquiteto edita o moodboard' using errcode = '42501';
  end if;
  return old;
end;
$$;
alter function public.moodboard_itens_guard() owner to postgres;
drop trigger if exists trg_moodboard_itens_guard on public.moodboard_itens;
create trigger trg_moodboard_itens_guard
  before insert or update or delete on public.moodboard_itens
  for each row execute function public.moodboard_itens_guard();
