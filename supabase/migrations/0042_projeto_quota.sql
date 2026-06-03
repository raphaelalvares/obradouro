-- 0042_projeto_quota.sql  (Fase 5 — quota de armazenamento UNIFICADA)
-- Achado adversarial CRÍTICO: cada guard somava SÓ a própria tabela → dava p/ burlar o limite
-- fragmentando (500MB em anexos + 500MB em moodboard + 500MB em revisões num plano de 500MB).
-- Correção: UMA função de consumo (anexos + moodboard_itens + revisao_arquivos) e UM guard genérico
-- usado pelos 3 triggers, com o MESMO advisory lock por tenant (serializa uploads concorrentes entre
-- módulos). meu_consumo (painel /me/quota) reusa a mesma função. tamanho_bytes já é o do 'full'
-- gravado (imagem reduzida) ou do raw (PDF) — contabilizado no backend.

-- (1) consumo total do tenant (as TRÊS tabelas). Só chamada por funções definer (guards/meu_consumo).
create or replace function public.consumo_armazenamento_bytes(p_tenant uuid)
returns bigint
language plpgsql stable security definer set search_path = '' as $$
declare v bigint;
begin
  select coalesce(sum(t.b), 0) into v from (
    select a.tamanho_bytes  as b from public.anexos          a  where a.tenant_id  = p_tenant
    union all
    select m.tamanho_bytes       from public.moodboard_itens m  where m.tenant_id  = p_tenant
    union all
    select ra.tamanho_bytes      from public.revisao_arquivos ra where ra.tenant_id = p_tenant
  ) t;
  return v;
end;
$$;
alter function public.consumo_armazenamento_bytes(uuid) owner to postgres;
revoke all on function public.consumo_armazenamento_bytes(uuid) from public, anon, authenticated;

-- (2) guard genérico de quota (todas as 3 tabelas têm tenant_id + tamanho_bytes). Mesmo lock key.
create or replace function public.enforce_quota_armazenamento()
returns trigger
language plpgsql security definer set search_path = '' as $$
declare
  v_limite_mb bigint;
  v_limite_b  bigint;
  v_usado     bigint;
begin
  v_limite_mb := public.plano_limite(new.tenant_id, 'armazenamento_mb');
  if v_limite_mb < 0 then
    return new;                                       -- ilimitado
  end if;
  perform pg_advisory_xact_lock(hashtext('cria:quota_armazenamento'), hashtext(new.tenant_id::text));
  v_limite_b := v_limite_mb * 1024 * 1024;
  v_usado := public.consumo_armazenamento_bytes(new.tenant_id);   -- anexos+moodboard+revisao
  if v_usado + new.tamanho_bytes > v_limite_b then
    raise exception 'limite_armazenamento:%:%', v_limite_mb, v_usado using errcode = 'P0001';
  end if;
  return new;
end;
$$;
alter function public.enforce_quota_armazenamento() owner to postgres;

-- (3) painel: consumo do PRÓPRIO tenant (reusa a função unificada).
create or replace function public.meu_consumo_armazenamento_bytes()
returns bigint
language plpgsql stable security definer set search_path = '' as $$
begin
  return public.consumo_armazenamento_bytes((select auth.uid()));
end;
$$;
alter function public.meu_consumo_armazenamento_bytes() owner to postgres;
revoke all on function public.meu_consumo_armazenamento_bytes() from public, anon;
grant execute on function public.meu_consumo_armazenamento_bytes() to authenticated;

-- (4) re-aponta o trigger de anexos p/ o guard genérico e liga os novos (ordem g < q < s por nome).
drop trigger if exists trg_anexos_quota on public.anexos;
create trigger trg_anexos_quota
  before insert on public.anexos
  for each row execute function public.enforce_quota_armazenamento();
drop function if exists public.anexos_quota_guard();   -- substituída pela genérica

drop trigger if exists trg_moodboard_itens_quota on public.moodboard_itens;
create trigger trg_moodboard_itens_quota
  before insert on public.moodboard_itens
  for each row execute function public.enforce_quota_armazenamento();

drop trigger if exists trg_revisao_arquivos_quota on public.revisao_arquivos;
create trigger trg_revisao_arquivos_quota
  before insert on public.revisao_arquivos
  for each row execute function public.enforce_quota_armazenamento();
