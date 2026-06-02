-- 0005_obra_seq_trigger.sql  (Fase 1)
-- Atribui seq_humano por tenant no INSERT de obras. UPDATE...RETURNING via ON CONFLICT
-- serializa só os inserts do MESMO tenant (lock de linha). Gaps por rollback são
-- aceitáveis (seq_humano é rótulo de exibição, não documento fiscal).

create or replace function public.assign_obra_seq()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_seq bigint;
begin
  -- idempotente: retry com mesmo uuid não renumera
  if new.seq_humano is not null then
    return new;
  end if;

  insert into public.obra_seq_counters as c (tenant_id, last_seq)
  values (new.tenant_id, 1)
  on conflict (tenant_id) do update
    set last_seq = c.last_seq + 1        -- lock de linha do tenant até o commit
  returning c.last_seq into v_seq;

  new.seq_humano := v_seq;
  return new;
end;
$$;

alter function public.assign_obra_seq() owner to postgres;   -- escreve no contador via isenção de owner

create trigger trg_assign_obra_seq
  before insert on public.obras
  for each row execute function public.assign_obra_seq();
