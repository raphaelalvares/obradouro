-- 0088_oportunidade_funil_obra.sql  (Comercial — DOIS funis: Projeto + Obra na mesma oportunidade)
--
-- O CRM passa a ter duas trilhas no MESMO card (decisão do usuário): o funil de PROJETO (vender o
-- projeto de arquitetura — `etapa`, reusa lead/contato/visita/proposta/ganho/perdido) e o funil de
-- OBRA (conversão p/ obra — `etapa_obra`, novo). Um lead pode entrar só-projeto, só-obra ou ambos:
--   * `etapa` NULL          → não está no funil de projeto (lead só-obra);
--   * `etapa_obra` NULL     → não está no funil de obra (lead só-projeto, ainda).
-- Ganhar o projeto NÃO é perda: o card fica `etapa='ganho'` e ABRE o funil de obra ('a_orcar') — isso
-- é feito no service (poka-yoke). O funil de obra é SINCRONIZADO com o orçamento (service): criar
-- versão → 'orcamento'; enviar → 'apresentado'; cliente aprova / virar-obra → 'ganho'. 'perdido' é
-- manual (uma recusa de versão não mata o negócio — pode vir R1).
--
-- Mexe em DUAS coisas que hoje vêm da 0079 (a vitória pelo aceite do cliente migra p/ o funil de obra):
--   (2) oportunidades_guard: a exceção do CLIENTE passa a liberar `etapa_obra → 'ganho'` (era `etapa`);
--   (3) decidir_orcamento_versao: ao aprovar, avança `etapa_obra` (era `etapa`).
-- Grants/RLS table-level já cobrem as colunas novas (0058). Greenfield: SEM backfill — linhas atuais
-- mantêm `etapa` (= no funil de projeto) e `etapa_obra` NULL. Aplicar como postgres, DEPOIS da 0087.
-- DEV antes de PROD.

begin;

-- ===================== (1) colunas dos dois funis =====================
-- `etapa` deixa de ser NOT NULL: NULL = card fora do funil de projeto (lead só-obra). O CHECK inline
-- da 0058 já aceita NULL (`null in (...)` → NULL, não-falso). `etapa_obra`/`valor_obra` são novos.
alter table public.oportunidades alter column etapa drop not null;

alter table public.oportunidades
  add column if not exists etapa_obra text,
  add column if not exists valor_obra numeric(14, 2);

alter table public.oportunidades drop constraint if exists oportunidades_etapa_obra_chk;
alter table public.oportunidades
  add constraint oportunidades_etapa_obra_chk
  check (etapa_obra is null
         or etapa_obra in ('a_orcar', 'orcamento', 'apresentado', 'ganho', 'perdido'));

alter table public.oportunidades drop constraint if exists oportunidades_valor_obra_chk;
alter table public.oportunidades
  add constraint oportunidades_valor_obra_chk
  check (valor_obra is null or valor_obra >= 0);

create index if not exists ix_oportunidades_tenant_etapa_obra
  on public.oportunidades (tenant_id, etapa_obra) where etapa_obra is not null;

-- ===================== (2) guard de oportunidades (base 0079 + exceção mira etapa_obra) =====================
-- Idêntico ao 0079, EXCETO a exceção do cliente: ao aprovar a proposta o cliente avança o funil de
-- OBRA (etapa_obra → 'ganho'), não mais o de projeto. As escritas do dono não usam allowlist por
-- subtração → as colunas novas passam livres.
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
    -- EXCEÇÃO: o CLIENTE do projeto vinculado vence o funil de OBRA (etapa_obra → 'ganho') ao aprovar
    -- a proposta. Só 'etapa_obra' muda; a RLS bloqueia o acesso direto → só a RPC definer chega aqui.
    if old.projeto_id is not null
       and new.etapa_obra = 'ganho'
       and public.meu_papel_projeto(old.projeto_id) = 'cliente'
       and (to_jsonb(new) - 'etapa_obra' - 'updated_at')
         = (to_jsonb(old) - 'etapa_obra' - 'updated_at')
    then
      return new;  -- avanço legítimo pelo cliente (funil de obra)
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

-- ===================== (3) RPC: cliente aprova → avança o funil de OBRA =====================
-- Idêntico ao 0079, EXCETO: ao aprovar, avança `etapa_obra` (era `etapa`); o lookup ignora obras já
-- terminais. Assinatura/retorno inalterados (a camada Python não muda).
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

  -- aprovado: vence o funil de OBRA da oportunidade vinculada (se houver e não terminal)
  if p_decisao = 'aprovado' then
    select o.id, o.seq_humano, o.nome
      into v_op_id, oportunidade_seq, oportunidade_nome
    from public.oportunidades o
    where o.projeto_id = p_projeto
          and (o.etapa_obra is null or o.etapa_obra not in ('ganho', 'perdido'))
    for update;
    if v_op_id is not null then
      update public.oportunidades set etapa_obra = 'ganho' where id = v_op_id;
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
      jsonb_build_object('por', 'aceite_orcamento', 'funil', 'obra'), oportunidade_nome,
      oportunidade_seq, null, p_projeto);
  end if;

  decisao := p_decisao;
  return next;
end;
$$;
alter function public.decidir_orcamento_versao(uuid, uuid, text, text) owner to postgres;
revoke all on function public.decidir_orcamento_versao(uuid, uuid, text, text) from public, anon;
grant execute on function public.decidir_orcamento_versao(uuid, uuid, text, text) to authenticated;

commit;
