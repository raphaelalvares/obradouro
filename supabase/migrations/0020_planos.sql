-- 0020_planos.sql  (Fase 2 — planos/limites: catálogo + assinatura + resolução)
-- Config CENTRALIZADA: trocar limite/flag/preço = UPDATE de 1 linha, nunca migração de dados.
-- A assinatura é do ARQUITETO (tenant). Desacoplado da cobrança (Fase 9).

-- Catálogo: o que cada plano oferece (limites e flags em jsonb).
create table if not exists public.planos (
  codigo      text        primary key,                 -- 'free','pro' (estável, referenciável)
  nome        text        not null,
  limites     jsonb       not null default '{}'::jsonb, -- {"obras_ativas":1,"revisoes_projeto":3}
  flags       jsonb       not null default '{}'::jsonb, -- {"export_pdf":false,...}
  ativo       boolean     not null default true,        -- descontinua p/ NOVOS, não remove de quem tem
  ordem       int         not null default 0,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
drop trigger if exists trg_planos_updated_at on public.planos;
create trigger trg_planos_updated_at
  before update on public.planos for each row execute function public.set_updated_at();

-- Seed (decisões: Free+Pro; -1 = ilimitado; TODAS as chaves presentes — ausência vira 0/bloqueio).
insert into public.planos (codigo, nome, limites, flags, ordem) values
  ('free', 'Free',
   '{"obras_ativas": 1,  "revisoes_projeto": 3}'::jsonb,
   '{"export_pdf": false, "logo": false, "chat": false, "historico": false}'::jsonb, 0),
  ('pro',  'Pro',
   '{"obras_ativas": -1, "revisoes_projeto": -1}'::jsonb,
   '{"export_pdf": true,  "logo": true,  "chat": true,  "historico": true}'::jsonb, 10)
on conflict (codigo) do update set            -- auto-corrige seed antigo (ex.: 2→4 flags)
  nome = excluded.nome, limites = excluded.limites, flags = excluded.flags, ordem = excluded.ordem;

-- Quem tem qual plano (1 linha por arquiteto). Sem assinatura => fallback 'free'.
create table if not exists public.tenant_assinaturas (
  tenant_id    uuid        primary key references public.profiles(id)  on delete cascade,
  plano_codigo text        not null     references public.planos(codigo) on delete restrict,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index if not exists ix_tenant_assinaturas_plano on public.tenant_assinaturas (plano_codigo);
drop trigger if exists trg_tenant_assinaturas_updated_at on public.tenant_assinaturas;
create trigger trg_tenant_assinaturas_updated_at
  before update on public.tenant_assinaturas for each row execute function public.set_updated_at();

-- RLS: default-deny (sem policy, sem grant a cria_app). Acesso só via as funções abaixo.
alter table public.planos              enable row level security;
alter table public.tenant_assinaturas  enable row level security;

-- Resolução do plano efetivo do tenant (assinatura -> catálogo; senão 'free').
create or replace function public.plano_do_tenant(p_tenant uuid)
returns table (codigo text, nome text, limites jsonb, flags jsonb)
language plpgsql stable security definer set search_path = '' as $$
begin
  return query
    select p.codigo, p.nome, p.limites, p.flags
    from public.planos p
    where p.codigo = coalesce(
      (select a.plano_codigo from public.tenant_assinaturas a where a.tenant_id = p_tenant),
      'free');
end; $$;
alter function public.plano_do_tenant(uuid) owner to postgres;
revoke all on function public.plano_do_tenant(uuid) from public, anon;
grant execute on function public.plano_do_tenant(uuid) to authenticated;

-- Limite numérico de um eixo (coalesce 0: eixo AUSENTE bloqueia — por isso o seed traz todas as chaves).
create or replace function public.plano_limite(p_tenant uuid, p_chave text)
returns bigint
language plpgsql stable security definer set search_path = '' as $$
declare v bigint;
begin
  select (pt.limites ->> p_chave)::bigint into v from public.plano_do_tenant(p_tenant) pt;
  return coalesce(v, 0);
end; $$;
alter function public.plano_limite(uuid, text) owner to postgres;
revoke all on function public.plano_limite(uuid, text) from public, anon;
grant execute on function public.plano_limite(uuid, text) to authenticated;

-- Flag booleana de funcionalidade (default false).
create or replace function public.plano_flag(p_tenant uuid, p_chave text)
returns boolean
language plpgsql stable security definer set search_path = '' as $$
declare v boolean;
begin
  select (pt.flags ->> p_chave)::boolean into v from public.plano_do_tenant(p_tenant) pt;
  return coalesce(v, false);
end; $$;
alter function public.plano_flag(uuid, text) owner to postgres;
revoke all on function public.plano_flag(uuid, text) from public, anon;
grant execute on function public.plano_flag(uuid, text) to authenticated;
