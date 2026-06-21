-- 0084_anexos_diario_tarefa_legenda.sql  (Fotos POR TAREFA no diário + legenda na foto)
--
-- Estende os anexos (polimórficos) p/ (1) aceitar 'diario_tarefa' como dono de foto — assim cada tarefa
-- medida no diário tem as SUAS fotos — e (2) ganhar uma LEGENDA editável. O anexo segue imutável em
-- tudo, EXCETO a legenda (corrigir um texto sem re-upload). Aplicar como postgres, DEPOIS da 0082/0083
-- (o ramo do guard referencia diario_tarefas). DEV antes de PROD.

begin;

-- ===================== (a) coluna legenda + parent_type novo =====================
alter table public.anexos add column if not exists legenda text;  -- tamanho validado no Pydantic

alter table public.anexos drop constraint if exists anexos_parent_type_check;
alter table public.anexos
  add constraint anexos_parent_type_check
  check (parent_type in ('etapa', 'checklist_item', 'diario', 'pendencia', 'diario_tarefa'));

-- ===================== (b) recriar anexos_guard (base VIVA 0066 + ramo + UPDATE-só-legenda) =====================
-- Cópia INTEGRAL do 0066 com: (1) ramo 'diario_tarefa' (FK em diario_tarefas da MESMA obra) no INSERT;
-- (2) UPDATE deixa de ser totalmente bloqueado → permite SÓ `legenda` (e updated_at) mudarem, por quem
-- executa (prestador só o próprio anexo). Todo o resto continua imutável.
create or replace function public.anexos_guard()
returns trigger
language plpgsql security definer set search_path = '' as $$
declare v_papel public.papel_obra;
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.obras o
                   where o.id = new.obra_id and o.tenant_id = new.tenant_id) then
      raise exception 'tenant_id/obra_id incoerentes' using errcode = '23514';
    end if;
    if new.parent_type = 'etapa' then
      if not exists (select 1 from public.etapas e
                     where e.id = new.parent_id and e.obra_id = new.obra_id) then
        raise exception 'etapa do anexo nao pertence a obra' using errcode = '23514';
      end if;
    elsif new.parent_type = 'checklist_item' then
      if not exists (select 1 from public.checklist_itens i
                     where i.id = new.parent_id and i.obra_id = new.obra_id) then
        raise exception 'item do anexo nao pertence a obra' using errcode = '23514';
      end if;
    elsif new.parent_type = 'diario' then
      if not exists (select 1 from public.diario_obra d
                     where d.id = new.parent_id and d.obra_id = new.obra_id) then
        raise exception 'diario do anexo nao pertence a obra' using errcode = '23514';
      end if;
    elsif new.parent_type = 'pendencia' then
      if not exists (select 1 from public.pendencias p
                     where p.id = new.parent_id and p.obra_id = new.obra_id) then
        raise exception 'pendencia do anexo nao pertence a obra' using errcode = '23514';
      end if;
    elsif new.parent_type = 'diario_tarefa' then
      if not exists (select 1 from public.diario_tarefas dt
                     where dt.id = new.parent_id and dt.obra_id = new.obra_id) then
        raise exception 'tarefa do diario do anexo nao pertence a obra' using errcode = '23514';
      end if;
    else
      raise exception 'parent_type invalido' using errcode = '23514';
    end if;
    if not public.pode_executar_obra(new.obra_id) then
      raise exception 'apenas quem executa a obra pode anexar' using errcode = '42501';
    end if;
    return new;
  end if;

  if tg_op = 'UPDATE' then
    -- anexo imutável EXCETO a legenda (corrigir texto sem re-upload).
    if (to_jsonb(new) - 'legenda' - 'updated_at')
       is distinct from
       (to_jsonb(old) - 'legenda' - 'updated_at') then
      raise exception 'anexo e imutavel exceto a legenda' using errcode = '42501';
    end if;
    v_papel := public.meu_papel_obra(old.obra_id);
    if v_papel = 'arquiteto' then
      return new;
    elsif v_papel = 'prestador' then
      if old.criado_por is distinct from (select auth.uid()) then
        raise exception 'prestador so edita a legenda do proprio anexo' using errcode = '42501';
      end if;
      return new;
    else
      raise exception 'sem permissao para editar anexo' using errcode = '42501';
    end if;
  end if;

  -- DELETE
  v_papel := public.meu_papel_obra(old.obra_id);
  if v_papel = 'arquiteto' then
    return old;
  elsif v_papel = 'prestador' then
    if old.criado_por is distinct from (select auth.uid()) then
      raise exception 'prestador so apaga o proprio anexo' using errcode = '42501';
    end if;
    return old;
  else
    raise exception 'sem permissao para apagar anexo' using errcode = '42501';
  end if;
end;
$$;
alter function public.anexos_guard() owner to postgres;
-- trigger trg_anexos_guard (0031) já aponta p/ esta função; não recriar.

-- ===================== (c) grant de UPDATE da legenda p/ cria_app =====================
-- O 0030 não deu UPDATE em anexos (o guard barrava tudo); agora a legenda é editável. Grant POR-COLUNA
-- (só legenda/updated_at) — o guard é o cinto fino, este é o nível de tabela.
grant update (legenda, updated_at) on public.anexos to cria_app;

-- ===================== (d) limpeza de órfãos ao apagar a tarefa-do-diário =====================
-- Apagar a medição some as fotos dela (a FK obra_id já cobre apagar a obra inteira). Reusa
-- anexos_limpar_orfaos (0032), que lê o parent_type de tg_argv[0].
drop trigger if exists trg_diario_tarefa_anexos_cleanup on public.diario_tarefas;
create trigger trg_diario_tarefa_anexos_cleanup
  after delete on public.diario_tarefas
  for each row execute function public.anexos_limpar_orfaos('diario_tarefa');

commit;
