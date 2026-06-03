-- 0033_anexos_quota.sql  (Fase 4 — eixo de plano: armazenamento)
-- Consumo = ESTADO DERIVADO (soma de anexos.tamanho_bytes por tenant), nunca um contador
-- materializado — mesma filosofia de obras_ativas (planos.py: "nunca dessincroniza").
-- (1) acrescenta a chave de limite ao catalogo (merge jsonb, idempotente);
-- (2) enforcement no DATA LAYER via trigger BEFORE INSERT (nao depende do service lembrar);
-- (3) leitura do proprio consumo p/ exibir no painel (sem vazar consumo de outro tenant).

-- (1) limite por plano (MB). free=500MB, pro=ilimitado (-1). Merge p/ nao reescrever flags/outras chaves.
update public.planos set limites = limites || jsonb_build_object('armazenamento_mb', 500)  where codigo = 'free';
update public.planos set limites = limites || jsonb_build_object('armazenamento_mb', -1)   where codigo = 'pro';

-- (2) trava de quota no INSERT de anexo. Dispara entre o guard e o seq (g < q < s na ordem de nome),
-- entao: coerencia/papel validados ANTES; e o seq NAO e queimado quando a quota estoura.
-- Advisory lock por tenant serializa o MESMO tenant (race entre uploads concorrentes). -1 = ilimitado.
-- Mensagem PARSEAVEL pelo backend: 'limite_armazenamento:<limite_mb>:<usado_bytes>' (P0001 generico).
create or replace function public.anexos_quota_guard()
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
  select coalesce(sum(a.tamanho_bytes), 0) into v_usado
  from public.anexos a where a.tenant_id = new.tenant_id;  -- inclui linhas ja inseridas nesta txn
  if v_usado + new.tamanho_bytes > v_limite_b then
    raise exception 'limite_armazenamento:%:%', v_limite_mb, v_usado using errcode = 'P0001';
  end if;
  return new;
end;
$$;
alter function public.anexos_quota_guard() owner to postgres;
drop trigger if exists trg_anexos_quota on public.anexos;
create trigger trg_anexos_quota
  before insert on public.anexos
  for each row execute function public.anexos_quota_guard();

-- (3) consumo do PROPRIO tenant (p/ o painel mostrar "X de Y MB"). Definer p/ somar mesmo o que a
-- RLS do chamador nao alcanca; usa auth.uid() (nunca um tenant arbitrario) => sem vazamento.
create or replace function public.meu_consumo_armazenamento_bytes()
returns bigint
language plpgsql stable security definer set search_path = '' as $$
declare v bigint;
begin
  select coalesce(sum(a.tamanho_bytes), 0) into v
  from public.anexos a where a.tenant_id = (select auth.uid());
  return v;
end;
$$;
alter function public.meu_consumo_armazenamento_bytes() owner to postgres;
revoke all on function public.meu_consumo_armazenamento_bytes() from public, anon;
grant execute on function public.meu_consumo_armazenamento_bytes() to authenticated;
