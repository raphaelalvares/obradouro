# Fase 1 — Desenho Concreto (CRIA)

> SaaS de gestão de obra para arquitetos. Backend FastAPI (Python 3.12, SQLAlchemy async + asyncpg), Postgres no Supabase. Arquitetura **API-ONLY**: apps falam só com a API; a API valida o JWT do Supabase e faz toda leitura/escrita. **RLS é a 2ª camada e PRECISA valer mesmo via backend.**

Este documento é o desenho acionável da Fase 1, pronto para gerar as migrations SQL e o código FastAPI. Decisões já travadas incorporadas: `updated_at` em toda tabela editável (function `public.set_updated_at()` já existe no baseline `0000`); UUID gerado no cliente; ID sequencial atribuído no servidor; RLS com role de aplicação dedicada (sem BYPASSRLS); conexão via Supavisor Session Pooler (5432).

---

## 0. Princípios de segurança que atravessam todo o desenho

1. **A role de conexão do backend NÃO faz BYPASS de RLS.** Conectar como `postgres`/owner ou qualquer role com `BYPASSRLS`/`SUPERUSER` ignora silenciosamente todas as policies. O backend conecta como uma role de *login* dedicada (`cria_app`), não-owner e sem `BYPASSRLS`.
2. **RLS segue o role EFETIVO corrente**, não o role de login. A garantia real de que a RLS vale vem de (a) o role corrente não ter `BYPASSRLS` e não ser dono das tabelas, **e** (b) `FORCE ROW LEVEL SECURITY` em todas as tabelas multi-tenant (defesa em profundidade — sujeita até o owner). Não confiamos na ideia de que "`SET ROLE` não reativa RLS"; aplicamos as duas barreiras.
3. **Contexto do usuário é TRANSACIONAL.** Cada request roda em uma transação explícita; o contexto (`request.jwt.claims`) é injetado com `set_config(..., true)` (= `SET LOCAL`), que é descartado no `COMMIT`/`ROLLBACK`. Isso é obrigatório no Supavisor Session Pooler porque a conexão do pool é reaproveitada entre requests de usuários diferentes — sem `LOCAL`, o contexto do usuário A vaza para o usuário B.
4. **Funções que quebram recursão de RLS são `plpgsql` (nunca `language sql`).** Funções SQL simples são *inlined* pelo planner; quando inlined, o contexto `SECURITY DEFINER` se perde e a recursão de RLS volta. `plpgsql` nunca é inlined. Devem ser `STABLE`, `SET search_path = ''`, com tudo schema-qualificado, e **owned por uma role com `BYPASSRLS`** (`postgres`) — é o `BYPASSRLS` do dono que efetivamente desliga a RLS dentro da função.
5. **JWT validado localmente** (assinatura/`exp`/`aud`/`iss`) com PyJWT + JWKS assimétrico, sem chamar o Auth server por request. O JWT só identifica a **pessoa** (`sub`). Papel e tenant do CRIA **não vêm do JWT** — vivem em `obra_membros`.

---

## 1. Modelo de dados final

### 1.1 Enums

```sql
-- 0001_enums.sql
create type public.papel_obra   as enum ('arquiteto', 'cliente', 'prestador');
create type public.estado_membro as enum ('pendente', 'ativo');
create type public.status_obra   as enum ('ativa', 'arquivada');
```

> Observação: enums são simples de ler mas rígidos para evoluir (adicionar valor é fácil, remover/renomear é caro). Para Fase 1 os domínios são estáveis, então enum nativo é aceitável. (Ver riscos em aberto, §9.)

### 1.2 `public.profiles` — identidade GLOBAL, 1:1 com `auth.users`

```sql
-- 0001_profiles.sql
create extension if not exists citext;

create table public.profiles (
  id          uuid        primary key references auth.users(id) on delete cascade,
  email       citext      not null unique,
  nome        text,
  telefone    text,                                  -- opcional
  created_by  uuid        references public.profiles(id) on delete set null,  -- só histórico
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create trigger trg_profiles_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();
```

- **PK = `auth.users.id`** (o `sub` do JWT). Sem CPF (minimização LGPD).
- Identidade **global e reutilizável** entre obras/arquitetos: tenant e papel NÃO ficam aqui.
- `email citext unique`: case-insensitive, uma conta por pessoa.
- `created_by` é só histórico de quem cadastrou pela 1ª vez; `on delete set null` para não bloquear a deleção do criador.

### 1.3 `public.obras` — tenant = arquiteto dono

```sql
-- 0002_obras.sql
create table public.obras (
  id          uuid          primary key,            -- gerado NO CLIENTE (offline)
  tenant_id   uuid          not null references public.profiles(id) on delete restrict,
  nome        text          not null,
  status      public.status_obra not null default 'ativa',
  seq_humano  bigint,                               -- atribuído NO SERVIDOR (trigger), por tenant
  created_at  timestamptz   not null default now(),
  updated_at  timestamptz   not null default now()
);

-- unicidade do rótulo humano por tenant (defesa em profundidade do contador)
create unique index uq_obras_tenant_seq on public.obras (tenant_id, seq_humano);
create index ix_obras_tenant on public.obras (tenant_id);

create trigger trg_obras_updated_at
  before update on public.obras
  for each row execute function public.set_updated_at();
```

- `id` é UUID gerado no cliente (suporte offline). Para retries idempotentes, o INSERT da obra usa `on conflict (id) do nothing` no backend.
- `tenant_id` = arquiteto dono. `on delete restrict` para não perder obras silenciosamente.
- `seq_humano` é nullable na definição porque é preenchido por trigger `BEFORE INSERT` (§5). É o **rótulo de exibição** (Obra #1, #2 por arquiteto), nunca o uuid.

### 1.4 `public.obra_membros` — associação pessoa↔obra (tenant + papel vivem aqui)

```sql
-- 0003_obra_membros.sql
create table public.obra_membros (
  id          uuid          primary key default gen_random_uuid(),
  obra_id     uuid          not null references public.obras(id)    on delete cascade,
  profile_id  uuid          not null references public.profiles(id) on delete cascade,
  papel       public.papel_obra    not null,
  estado      public.estado_membro not null default 'pendente',
  invited_by  uuid          references public.profiles(id) on delete set null,
  created_at  timestamptz   not null default now(),
  updated_at  timestamptz   not null default now(),
  constraint uq_obra_membro unique (obra_id, profile_id)   -- 1 pessoa = 1 vínculo por obra
);

-- Índices que sustentam a RLS (CRÍTICOS):
create index ix_obra_membros_profile_estado on public.obra_membros (profile_id, estado);  -- cobre o lookup da função
create index ix_obra_membros_obra           on public.obra_membros (obra_id);

create trigger trg_obra_membros_updated_at
  before update on public.obra_membros
  for each row execute function public.set_updated_at();
```

- Uma pessoa pode estar em várias obras com papéis diferentes; `unique (obra_id, profile_id)` garante 1 vínculo por par.
- `estado` controla `pendente` → `ativo` (aceite). Pendente NÃO vê dados da obra (§2.5).
- O criador da obra entra como `papel='arquiteto', estado='ativo'` na **mesma transação** do INSERT da obra (backend).

### 1.5 `public.obra_seq_counters` — contador por tenant (suporte ao §5)

```sql
-- 0004_obra_seq_counters.sql
create table public.obra_seq_counters (
  tenant_id uuid   primary key references public.profiles(id) on delete cascade,
  last_seq  bigint not null default 0
);
-- RLS habilitada e SEM policy permissiva: ninguém mexe direto, só o trigger SECURITY DEFINER.
alter table public.obra_seq_counters enable row level security;
alter table public.obra_seq_counters force  row level security;
```

### 1.6 `public.obra_codigos` — código de obra (suporte ao §7)

```sql
-- 0006_obra_codigos.sql
create table public.obra_codigos (
  id          uuid        primary key default gen_random_uuid(),
  obra_id     uuid        not null references public.obras(id) on delete cascade,
  codigo      text        not null,                 -- token curto, legível; ver §7
  papel       public.papel_obra not null,           -- papel concedido ao entrar
  expires_at  timestamptz not null,                 -- now() + interval '24 hours'
  revoked_at  timestamptz,                           -- revogação manual pelo arquiteto
  created_by  uuid        not null references public.profiles(id) on delete restrict,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
-- só um código ATIVO por obra de cada vez: regenerar revoga o anterior (app), índice parcial garante:
create unique index uq_obra_codigo_ativo
  on public.obra_codigos (obra_id)
  where revoked_at is null;
create unique index uq_obra_codigo_valor on public.obra_codigos (codigo);
create index ix_obra_codigos_obra on public.obra_codigos (obra_id);

create trigger trg_obra_codigos_updated_at
  before update on public.obra_codigos
  for each row execute function public.set_updated_at();
```

> "Uso único por pessoa" não é uma flag no código e sim consequência do `unique (obra_id, profile_id)` em `obra_membros`: tentar entrar de novo na mesma obra colide. O código em si é reutilizável por **pessoas diferentes** até expirar/ser revogado.

### 1.7 `public.audit_log` — CORE, append-only, 2 camadas

```sql
-- 0007_audit_log.sql  (criar como OWNER privilegiado = postgres, NÃO como cria_app)
create table public.audit_log (
  id            uuid primary key default gen_random_uuid(),
  -- camada de sistema (cru/factual, imutável):
  tenant_id     uuid        not null,
  actor_id      uuid,                                  -- profiles.id do ator (null = sistema)
  obra_id       uuid,                                  -- para RLS por obra (null = evento sem obra)
  action        text        not null,                  -- ex.: 'obra.arquivada'
  entity_type   text        not null,                  -- ex.: 'obra'
  entity_id     uuid        not null,
  changed       jsonb,                                 -- {"status":{"de":"ativa","para":"arquivada"}}
  -- camada de exibição (snapshot CONGELADO no momento do evento):
  entity_label  text        not null,                  -- 'Reforma Apto 302'
  entity_seq    bigint,                                -- 42  (o #seq_humano; NUNCA o uuid na UI)
  actor_label   text,                                  -- nome do ator naquele instante
  created_at    timestamptz not null default now()
);
create index ix_audit_tenant_created on public.audit_log (tenant_id, created_at desc);
create index ix_audit_obra           on public.audit_log (obra_id);  -- sustenta RLS por obra
create index ix_audit_entity         on public.audit_log (entity_type, entity_id);
```

Imutabilidade detalhada em §6.

---

## 2. Estratégia de RLS

Habilitar **e forçar** RLS em todas as tabelas multi-tenant:

```sql
-- 0010_rls_enable.sql
alter table public.profiles      enable row level security;
alter table public.profiles      force  row level security;
alter table public.obras         enable row level security;
alter table public.obras         force  row level security;
alter table public.obra_membros  enable row level security;
alter table public.obra_membros  force  row level security;
alter table public.obra_codigos  enable row level security;
alter table public.obra_codigos  force  row level security;
alter table public.audit_log     enable row level security;
alter table public.audit_log     force  row level security;
-- obra_seq_counters já habilitada/forçada em 0004
```

### 2.1 Função central que quebra a recursão (`current_obra_ids`)

```sql
-- 0011_rls_functions.sql
-- plpgsql (NUNCA language sql: seria inlined e a recursão voltaria), STABLE, search_path travado.
-- DEVE ser owned por role com BYPASSRLS (postgres) — é o BYPASSRLS do dono que desliga a RLS aqui dentro.
create or replace function public.current_obra_ids()
returns setof uuid
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  return query
    select om.obra_id
    from public.obra_membros om
    where om.profile_id = (select auth.uid())
      and om.estado = 'ativo';        -- pendente NUNCA entra na lista de obras "visíveis"
end;
$$;

alter function public.current_obra_ids() owner to postgres;          -- BYPASSRLS efetivo
revoke all on function public.current_obra_ids() from public, anon;
grant execute on function public.current_obra_ids() to authenticated;
```

> `auth.uid()` (definição oficial do Supabase) resolve `nullif(coalesce(current_setting('request.jwt.claim.sub', true), (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')), '')::uuid`. Logo, quando o backend faz `set_config('request.jwt.claims', ..., true)`, `auth.uid()` funciona normalmente. O `nullif(...,'')` trata o "empty string" que sobra na GUC após o COMMIT.

### 2.2 RLS em `profiles`

Identidade global: cada um vê/edita o próprio perfil; e vê perfis de pessoas com quem compartilha obra ativa (para renderizar nomes de membros).

```sql
-- 0012_rls_profiles.sql
create policy profiles_select on public.profiles
  for select to authenticated
  using (
        id = (select auth.uid())
     or id in (
          select om.profile_id
          from public.obra_membros om
          where om.obra_id in (select public.current_obra_ids())
        )
  );

create policy profiles_update on public.profiles
  for update to authenticated
  using      ( id = (select auth.uid()) )
  with check ( id = (select auth.uid()) );

-- INSERT da profile: feito pelo backend logo após criar o auth.user (UPSERT). O próprio dono insere a si:
create policy profiles_insert on public.profiles
  for insert to authenticated
  with check ( id = (select auth.uid()) );
```

> O trigger `handle_new_user` (§abaixo) e a Admin API rodam em contexto privilegiado, fora dessa policy. A policy cobre o UPSERT do backend quando ele já estiver conectado como `cria_app`.

### 2.3 RLS em `obras` (só obra ATIVA aparece para o membro)

```sql
-- 0013_rls_obras.sql
create policy obras_select on public.obras
  for select to authenticated
  using ( id in (select public.current_obra_ids()) );

create policy obras_insert on public.obras
  for insert to authenticated
  -- criador é dono; o vínculo arquiteto/ativo é criado na mesma transação pelo backend
  with check ( tenant_id = (select auth.uid()) );

create policy obras_update on public.obras
  for update to authenticated
  using      ( id in (select public.current_obra_ids()) )
  with check ( id in (select public.current_obra_ids()) );

-- sem policy de DELETE: obra não se deleta (arquiva-se). DELETE fica negado por default.
```

> Pendente nunca entra em `current_obra_ids()` (filtra `estado='ativo'`), então pendente **não enxerga a obra** por aqui — só pelo rótulo magro do §2.5.

### 2.4 RLS em `obra_membros` (sem auto-join recursivo)

A leitura passa pela função `SECURITY DEFINER`, evitando a recursão clássica (policy em `obra_membros` consultando `obra_membros` diretamente).

```sql
-- 0014_rls_obra_membros.sql
-- vê membros das obras onde você é ativo  OU  sua própria linha (inclusive PENDENTE)
create policy obra_membros_select on public.obra_membros
  for select to authenticated
  using (
        obra_id in (select public.current_obra_ids())
     or profile_id = (select auth.uid())
  );

-- INSERT/UPDATE de membros é responsabilidade do backend (convite/aceite/papel).
-- Permitir que arquiteto ATIVO da obra gerencie membros; e que a pessoa aceite a PRÓPRIA linha.
create policy obra_membros_insert on public.obra_membros
  for insert to authenticated
  with check ( obra_id in (select public.current_obra_ids()) );

create policy obra_membros_update on public.obra_membros
  for update to authenticated
  using (
        obra_id in (select public.current_obra_ids())   -- arquiteto ativo da obra
     or profile_id = (select auth.uid())                 -- a própria pessoa (aceitar convite)
  )
  with check (
        obra_id in (select public.current_obra_ids())
     or profile_id = (select auth.uid())
  );
```

> A regra de negócio fina (só `arquiteto` pode adicionar/remover membros; pessoa só pode mudar o próprio `estado` de `pendente`→`ativo`, não o `papel`) é validada **na API** (camada 1). A RLS é a rede grossa (camada 2). Quem entra como criador da obra precisa do `INSERT` do próprio vínculo arquiteto **antes** de aparecer em `current_obra_ids()` — por isso o INSERT da obra + INSERT do membro arquiteto rodam na mesma transação, e a verificação de "é arquiteto" é da API; a policy de INSERT acima permite o segundo membro em diante via `current_obra_ids()`. Para o **primeiro** vínculo (o do criador) que ainda não está em `current_obra_ids()`, o INSERT é feito via função `SECURITY DEFINER` `criar_obra(...)` (ver §7/§8 nota) que cria obra + vínculo arquiteto atomicamente.

### 2.5 Caso PENDENTE (só vê nome da obra + quem convidou)

Pendente **não** recebe acesso a `obras` nem às filhas. O rótulo magro sai por função dedicada cujo escopo está no **próprio WHERE** (não confiamos na RLS da tabela-base):

```sql
-- 0015_rls_pendentes.sql
create or replace function public.minhas_obras_pendentes()
returns table (obra_id uuid, obra_nome text, seq_humano bigint, invited_by_nome text)
language plpgsql
stable
security definer
set search_path = ''
as $$
begin
  return query
    select o.id, o.nome, o.seq_humano, p.nome
    from public.obra_membros om
    join public.obras    o on o.id = om.obra_id
    left join public.profiles p on p.id = om.invited_by
    where om.profile_id = (select auth.uid())     -- escopo no WHERE, não no RLS da base
      and om.estado = 'pendente';
end;
$$;
alter function public.minhas_obras_pendentes() owner to postgres;
revoke all on function public.minhas_obras_pendentes() from public, anon;
grant execute on function public.minhas_obras_pendentes() to authenticated;
```

> Como uma view comum roda com direitos do dono e ignora a RLS das bases, qualquer view alternativa para isso deve igualmente carregar o filtro `profile_id = auth.uid() AND estado='pendente'` no WHERE (ou usar `security_invoker=on` em PG15+). A função acima é a forma preferida.

### 2.6 RLS em `obra_codigos`

```sql
-- 0016_rls_obra_codigos.sql
-- só arquiteto ATIVO da obra enxerga/gerencia códigos da própria obra
create policy obra_codigos_all on public.obra_codigos
  for all to authenticated
  using      ( obra_id in (select public.current_obra_ids()) )
  with check ( obra_id in (select public.current_obra_ids()) );
```

> O **consumo** do código (alguém de fora entrando na obra) NÃO passa por esta policy — quem está entrando ainda não é membro. Esse fluxo é feito por função `SECURITY DEFINER` `resgatar_codigo_obra(codigo)` (§7), que valida e cria o vínculo pendente.

### 2.7 RLS em `audit_log` (imutável — só SELECT por obra/tenant)

```sql
-- 0017_rls_audit.sql
create policy audit_select on public.audit_log
  for select to authenticated
  using (
        obra_id in (select public.current_obra_ids())
     or (obra_id is null and tenant_id = (select auth.uid()))  -- eventos sem obra do próprio tenant
  );
-- SEM policy de INSERT/UPDATE/DELETE para authenticated: escrita só via função SECURITY DEFINER (§6).
-- Com RLS ligado e sem policy, o default é DENY -> reforça o append-only.
```

---

## 3. Role de aplicação + contexto por request

### 3.1 SQL da role dedicada (rodar em contexto privilegiado)

```sql
-- 0009_app_role.sql  (aplicar no SQL Editor / contexto privilegiado)
-- Role de LOGIN dedicada: NÃO owner, NÃO superuser, SEM BYPASSRLS.
create role cria_app login password '***';     -- defina via secret; nunca commitar
grant authenticated to cria_app;               -- pode assumir o role 'authenticated' do Supabase

-- Grants mínimos (o 'authenticated' do Supabase já traz os grants padrão de schema;
-- explicitar o necessário para o backend):
grant usage on schema public to cria_app;
grant select, insert, update on
  public.profiles, public.obras, public.obra_membros, public.obra_codigos to cria_app;
-- audit_log: SOMENTE select direto (insert é via função SECURITY DEFINER):
grant select on public.audit_log to cria_app;
-- nunca grant update/delete/truncate em audit_log; nunca grant em obra_seq_counters.
```

> O backend abre a conexão como `cria_app`. As tabelas são owned por `postgres` (migrations), portanto `FORCE RLS` sujeita o owner também e `cria_app` (sem BYPASSRLS) sempre passa pelas policies.

### 3.2 Snippet Python — contexto do usuário por request (SQLAlchemy async)

```python
# db.py
import json
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Conecta SEMPRE como cria_app (NUNCA postgres/owner). Supavisor Session Pooler = porta 5432.
engine = create_async_engine(
    "postgresql+asyncpg://cria_app:***@<project>.pooler.supabase.com:5432/postgres",
    pool_pre_ping=True,
    # asyncpg em Session pooler (5432) suporta prepared statements; em Transaction mode (6543)
    # seria necessário connect_args={"statement_cache_size": 0}. Ficamos no 5432.
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def set_rls_context(session: AsyncSession, claims: dict) -> None:
    """Chamar logo após abrir a sessão, DENTRO da transação do request.
    is_local=true => escopo de TRANSAÇÃO (descartado no commit/rollback) => sem vazamento no pool.
    """
    # Passa ao Postgres apenas o mínimo já validado:
    minimal = json.dumps({"sub": claims["sub"], "role": "authenticated", "email": claims.get("email")})
    await session.execute(text("SET LOCAL ROLE authenticated"))   # 'authenticated' é literal seguro
    await session.execute(
        text("SELECT set_config('request.jwt.claims', :c, true)"),  # true = LOCAL/transacional
        {"c": minimal},                                             # SEMPRE bind param (nunca f-string)
    )


async def get_db(claims: dict):
    """Dependência FastAPI: 1 request = 1 AsyncSession = 1 transação (vale também p/ SELECT puro)."""
    async with SessionLocal() as session:
        async with session.begin():                 # transação EXPLÍCITA — sem ela SET LOCAL não tem efeito
            await set_rls_context(session, claims)
            yield session
        # COMMIT/ROLLBACK aqui descarta o SET LOCAL automaticamente
```

Notas de robustez:
- **Transação explícita é obrigatória inclusive para leituras**: sem ela, `SET LOCAL` não vale e `auth.uid()` volta NULL → as policies negam tudo.
- Em SQLAlchemy 2.0.17+, **não** emitir `session.execute()` dentro do evento `after_begin` (lança `InvalidRequestError`, "concurrent operations not permitted"). Se quiser usar eventos, emita via `connection.execute()` no `after_begin`; por simplicidade, preferimos setar o contexto explicitamente no início da dependência, como acima.
- Quem injeta `claims` na dependência é a verificação de JWT (§4).

---

## 4. Validação de JWT no FastAPI

**Abordagem:** validação **local** do access token com **chaves assimétricas** (JWKS), sem chamar `getUser()` por request. Default da plataforma para chaves assimétricas é **RS256**; **ES256** (P-256) é a escolha preferida por performance (chave/assinatura menores), mas **não** é o que o projeto recebe por default — configure os `algorithms` conforme o `alg` que **seu** projeto realmente emite (verifique em Dashboard → JWT Keys / no `alg` do JWKS). Projetos novos (desde 01/10/2025) já nascem assimétricos; HS256 legado é "not recommended for production".

```python
# auth.py
import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SUPABASE_PROJECT_REF = "abcdefghijklmnopqrst"
ISSUER   = f"https://{SUPABASE_PROJECT_REF}.supabase.co/auth/v1"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"

# UMA instância global (escopo de app): cacheia o JWK Set (default ~300s) e refaz fetch se o kid
# do token não estiver no cache (cobre rotação de chave). cache_keys fica False (default) para não
# servir chave revogada indefinidamente.
_jwks_client = PyJWKClient(JWKS_URL)

bearer = HTTPBearer(auto_error=True)


def verify_supabase_jwt(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    token = cred.credentials
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],   # SÓ assimétrico; NUNCA incluir HS256 (algorithm confusion)
            audience="authenticated",
            issuer=ISSUER,
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}")
    return claims   # claims["sub"] = profiles.id ; claims.get("email")
```

E a composição com o DB (a dependência de DB consome os claims já verificados):

```python
# deps.py
from fastapi import Depends
from auth import verify_supabase_jwt
from db import get_db

async def db_session(claims: dict = Depends(verify_supabase_jwt)):
    async for s in get_db(claims):
        yield s
```

Pontos travados:
- **Lista fixa de algoritmos, sem HS256 junto** com assimétricos (evita *algorithm confusion*).
- **Valide `aud='authenticated'` e `iss`** sempre. Se ativar custom domain, confira o `iss` real emitido no token e ajuste `ISSUER`.
- O JWT **só autentica a pessoa** (`sub`). Papel/tenant (`arquiteto/cliente/prestador`) **não** vêm do JWT — autorização por obra/papel é API + RLS.
- Validação local não detecta logout/revogação antes do `exp`; mantenha access tokens curtos (~1h) + refresh. Revogação imediata exigiria checagem extra (fora da Fase 1).

---

## 5. Função de ID sequencial por tenant

Estratégia: **tabela de contadores** (1 linha por arquiteto) + **trigger `BEFORE INSERT`** em `obras`. O `UPDATE ... RETURNING` (via `ON CONFLICT DO UPDATE`) pega lock de linha que serializa **só** os inserts do mesmo tenant — dois arquitetos criam obras em paralelo sem se bloquear.

Por que não sequence nativa: é global (não por-tenant), `nextval` nunca reverte em rollback ("cannot be used to obtain gapless sequences"), e uma sequence por arquiteto não escala. `seq_humano` é rótulo de exibição, então **gaps raros de rollback são aceitáveis** — não perseguimos gapless estrito.

```sql
-- 0005_obra_seq_trigger.sql
create or replace function public.assign_obra_seq()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_seq bigint;
begin
  -- idempotente: se o número já veio (retry com mesmo uuid), não renumera
  if new.seq_humano is not null then
    return new;
  end if;

  insert into public.obra_seq_counters as c (tenant_id, last_seq)
  values (new.tenant_id, 1)
  on conflict (tenant_id) do update
    set last_seq = c.last_seq + 1        -- UPDATE => lock de linha do tenant até o commit
  returning c.last_seq into v_seq;

  new.seq_humano := v_seq;
  return new;
end;
$$;
alter function public.assign_obra_seq() owner to postgres;   -- precisa escrever no contador

create trigger trg_assign_obra_seq
  before insert on public.obras
  for each row execute function public.assign_obra_seq();
```

- Trigger garante 1 fonte de verdade no banco, independente de quantos caminhos inserem obra. Roda na mesma transação do INSERT, então o número só se materializa se a obra for gravada.
- `obra_seq_counters` tem RLS forçada e **sem policy** para `cria_app`: ninguém escreve direto, só o trigger (`SECURITY DEFINER`, owner `postgres`).
- Não usar `LOCK TABLE`/linha-contadora global (serializaria todos os tenants e poderia esgotar o pool). A chave por `tenant_id` distribui a contenção.

---

## 6. Audit log — imutabilidade e como a aplicação grava

**Três camadas de defesa (append-only):**

1. **Privilégio** (primária): `audit_log` é owned por `postgres`; `cria_app` recebe **só** `SELECT` (o INSERT vai por função `SECURITY DEFINER`). Sem `UPDATE`/`DELETE`/`TRUNCATE`. O código fisicamente não consegue mutar uma linha — mesmo com bug ou SQL injection.
2. **Trigger que bloqueia** (belt-and-suspenders): protege contra um `GRANT` vazado numa migration futura.
3. **RLS default-deny + FORCE**: RLS ligado, só policy de SELECT (§2.7); INSERT/UPDATE/DELETE negados por default; `FORCE` sujeita até o owner.

```sql
-- 0008_audit_immutability.sql  (rodar como postgres)
revoke insert, update, delete, truncate on public.audit_log from cria_app;
grant  select on public.audit_log to cria_app;

create or replace function public.audit_log_block_mutation()
returns trigger language plpgsql as $$
begin
  raise exception 'audit_log e append-only: % nao permitido', tg_op
    using errcode = '0A000';   -- feature_not_supported
end $$;

create trigger trg_audit_no_update
  before update on public.audit_log
  for each row execute function public.audit_log_block_mutation();
create trigger trg_audit_no_delete
  before delete on public.audit_log
  for each row execute function public.audit_log_block_mutation();
-- TRUNCATE ignora RLS e triggers BEFORE DELETE row-level; revogado acima por privilégio.

-- Caminho de escrita ÚNICO (SECURITY DEFINER, owner postgres):
create or replace function public.cria_audit_log(
  p_tenant uuid, p_actor uuid, p_obra uuid, p_action text, p_entity_type text,
  p_entity_id uuid, p_changed jsonb, p_entity_label text,
  p_entity_seq bigint, p_actor_label text)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.audit_log
    (tenant_id, actor_id, obra_id, action, entity_type, entity_id, changed,
     entity_label, entity_seq, actor_label)
  values
    (p_tenant, p_actor, p_obra, p_action, p_entity_type, p_entity_id, p_changed,
     p_entity_label, p_entity_seq, p_actor_label);
end $$;
alter function public.cria_audit_log(uuid,uuid,uuid,text,text,uuid,jsonb,text,bigint,text) owner to postgres;
revoke all on function public.cria_audit_log(uuid,uuid,uuid,text,text,uuid,jsonb,text,bigint,text) from public, anon;
grant execute on function public.cria_audit_log(uuid,uuid,uuid,text,text,uuid,jsonb,text,bigint,text) to authenticated;
```

**Como a aplicação grava (gravação EXPLÍCITA, não trigger genérico):** o `audit_log` do CRIA é um log de **ações de negócio** (arquivou obra, aceitou convite, revogou código), não um espelho de linhas. Eventos sem mutação de tabela (convite enviado, código gerado/revogado) seriam invisíveis a um trigger genérico. Toda escrita é centralizada num **único serviço de auditoria** (coberto por testes), que monta o snapshot legível e chama `cria_audit_log` **na mesma transação** da mutação de domínio:

```python
# audit.py
import json
from sqlalchemy import text

async def log_event(session, *, tenant, actor_id, obra_id, action, entity_type,
                    entity_id, changed: dict, entity_label, entity_seq, actor_label):
    await session.execute(
        text("""select public.cria_audit_log(
                 :tenant, :actor, :obra, :action, :etype, :eid, cast(:changed as jsonb),
                 :elabel, :eseq, :alabel)"""),
        {
            "tenant": tenant, "actor": actor_id, "obra": obra_id,
            "action": action, "etype": entity_type, "eid": entity_id,
            "changed": json.dumps(changed),
            "elabel": entity_label,   # snapshot CONGELADO agora (nome no instante do evento)
            "eseq": entity_seq,       # #seq_humano congelado; NUNCA o uuid na UI
            "alabel": actor_label,    # nome do ator no instante
        },
    )
```

Regras: **snapshot congelado no INSERT** (nunca re-hidratar via JOIN ao vivo — senão o log "mente" quando a obra é renomeada/arquivada). UI exibe `entity_label (#entity_seq)`, **nunca** o uuid. Renderiza "João arquivou a obra Reforma Apto 302 (#42) em 02/06" sem hydration ao vivo.

---

## 7. Vínculo pessoa↔obra (duas portas, um mecanismo)

Estados: pessoa entra **`pendente`** → vira **`ativo`** com aceite. Pendente só vê `{obra_nome, seq_humano, invited_by_nome}` (via `minhas_obras_pendentes()`, §2.5).

### Porta 1 — Convite por email
1. Arquiteto ativo da obra chama `POST /obras/{id}/convites` com `{email, papel}`.
2. Backend resolve/cria a `profile` por email (Admin API se a pessoa ainda não existe; `invite_user_by_email`/`generate_link`), faz UPSERT da profile, e cria `obra_membros (obra_id, profile_id, papel, estado='pendente', invited_by=ator)`.
3. `unique (obra_id, profile_id)` impede convite duplicado para a mesma obra.
4. Pessoa aceita: `POST /convites/{membro_id}/aceitar` → `estado='ativo'`. Auditar `convite.aceito`.

### Porta 2 — Código de obra
- **Geração** (`POST /obras/{id}/codigo`): cria `obra_codigos` com `expires_at = now() + interval '24 hours'`, `papel` definido pelo arquiteto. O índice parcial `uq_obra_codigo_ativo` + revogação garantem **um código ativo por obra**.
- **Revogação/Regeneração** (`DELETE`/`POST` de código): seta `revoked_at = now()` no anterior e cria novo. Auditar `codigo.revogado` / `codigo.gerado`.
- **Expiração:** 24h, via `expires_at`. Validação no resgate.
- **Resgate** (pessoa de fora entra): função `SECURITY DEFINER` porque quem entra **ainda não é membro** (não passa pela RLS de `obra_codigos`):

```sql
-- 0018_resgatar_codigo.sql
create or replace function public.resgatar_codigo_obra(p_codigo text)
returns uuid                      -- retorna obra_id em caso de sucesso
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_obra   uuid;
  v_papel  public.papel_obra;
  v_inviter uuid;
  v_membro uuid;
begin
  select c.obra_id, c.papel, c.created_by
    into v_obra, v_papel, v_inviter
  from public.obra_codigos c
  where c.codigo = p_codigo
    and c.revoked_at is null
    and c.expires_at > now()
  for share;                       -- evita corrida com revogação

  if v_obra is null then
    raise exception 'codigo invalido ou expirado' using errcode = '22023';
  end if;

  -- uso único POR PESSOA: o unique(obra_id,profile_id) impede entrar 2x na mesma obra
  insert into public.obra_membros (obra_id, profile_id, papel, estado, invited_by)
  values (v_obra, (select auth.uid()), v_papel, 'pendente', v_inviter)
  on conflict (obra_id, profile_id) do nothing
  returning id into v_membro;

  return v_obra;
end;
$$;
alter function public.resgatar_codigo_obra(text) owner to postgres;
revoke all on function public.resgatar_codigo_obra(text) from public, anon;
grant execute on function public.resgatar_codigo_obra(text) to authenticated;
```

> Após resgatar, a pessoa fica `pendente` e enxerga só o rótulo da obra. Em ambas as portas, o aceite (`pendente`→`ativo`) é uma ação explícita auditada.

### Nota — criação atômica de obra (criador vira arquiteto)
Como o criador ainda não está em `current_obra_ids()` no momento do INSERT da obra, criar obra + vínculo arquiteto ativo é feito por função `SECURITY DEFINER` `criar_obra(p_id uuid, p_nome text)` que insere a obra (com `tenant_id = auth.uid()`) e o `obra_membros (papel='arquiteto', estado='ativo')` na mesma transação, e chama `cria_audit_log`. Isso evita o ovo-e-galinha da policy de INSERT em `obra_membros`.

---

## 8. Endpoints da Fase 1

Autenticação: todos exigem `Authorization: Bearer <access_token>` (validado em §4). "Papel" abaixo é a autorização de negócio (camada 1), reforçada pela RLS (camada 2).

| Método | Caminho | Quem pode | Descrição |
|---|---|---|---|
| GET | `/me` | qualquer autenticado | Perfil do usuário corrente |
| PATCH | `/me` | dono | Atualiza nome/telefone do próprio perfil |
| POST | `/obras` | qualquer autenticado | Cria obra (vira arquiteto/ativo); UUID do cliente; `seq_humano` no servidor |
| GET | `/obras` | membro ativo | Lista obras onde é membro ativo |
| GET | `/obras/{id}` | membro ativo da obra | Detalhe da obra |
| PATCH | `/obras/{id}` | arquiteto da obra | Renomear |
| POST | `/obras/{id}/arquivar` | arquiteto da obra | `status` → `arquivada` (auditado) |
| POST | `/obras/{id}/reativar` | arquiteto da obra | `status` → `ativa` (auditado) |
| GET | `/obras/{id}/membros` | membro ativo da obra | Lista membros |
| POST | `/obras/{id}/convites` | arquiteto da obra | Convite por email (`{email, papel}`) → membro pendente |
| DELETE | `/obras/{id}/membros/{membro_id}` | arquiteto da obra | Remove membro |
| POST | `/obras/{id}/codigo` | arquiteto da obra | Gera/regenera código (24h, revoga anterior) |
| GET | `/obras/{id}/codigo` | arquiteto da obra | Código ativo atual |
| DELETE | `/obras/{id}/codigo` | arquiteto da obra | Revoga código ativo |
| GET | `/me/convites-pendentes` | qualquer autenticado | `minhas_obras_pendentes()` (nome + seq + quem convidou) |
| POST | `/convites/{membro_id}/aceitar` | a própria pessoa pendente | `pendente` → `ativo` (auditado) |
| POST | `/codigo/resgatar` | qualquer autenticado | `resgatar_codigo_obra(codigo)` → entra pendente |
| GET | `/obras/{id}/audit` | membro ativo da obra | Log de exibição (snapshot; nunca uuid) |

---

## 9. Divisão das migrations e riscos/decisões em aberto

### 9.1 Ordem dos arquivos `.sql`

| Ordem | Arquivo | Conteúdo |
|---|---|---|
| 0000 | *(baseline existente)* | já contém `public.set_updated_at()` |
| 0001 | `0001_enums_profiles.sql` | extensão `citext`; enums (`papel_obra`, `estado_membro`, `status_obra`); `profiles` + trigger `updated_at`; trigger `handle_new_user` em `auth.users` (rede de segurança, ver nota) |
| 0002 | `0002_obras.sql` | `obras` + índices + trigger `updated_at` |
| 0003 | `0003_obra_membros.sql` | `obra_membros` + índices (`profile_id,estado` / `obra_id`) + trigger |
| 0004 | `0004_obra_seq_counters.sql` | `obra_seq_counters` (RLS enable+force, sem policy) |
| 0005 | `0005_obra_seq_trigger.sql` | `assign_obra_seq()` + trigger `BEFORE INSERT` em `obras` |
| 0006 | `0006_obra_codigos.sql` | `obra_codigos` + índices + trigger |
| 0007 | `0007_audit_log.sql` | `audit_log` + índices (owner postgres) |
| 0008 | `0008_audit_immutability.sql` | revokes, triggers de bloqueo, `cria_audit_log()` |
| 0009 | `0009_app_role.sql` | role `cria_app` + grants |
| 0010 | `0010_rls_enable.sql` | `enable`+`force` RLS em todas as tabelas multi-tenant |
| 0011 | `0011_rls_functions.sql` | `current_obra_ids()` (plpgsql, owner postgres, BYPASSRLS) |
| 0012 | `0012_rls_profiles.sql` | policies de `profiles` |
| 0013 | `0013_rls_obras.sql` | policies de `obras` |
| 0014 | `0014_rls_obra_membros.sql` | policies de `obra_membros` |
| 0015 | `0015_rls_pendentes.sql` | `minhas_obras_pendentes()` |
| 0016 | `0016_rls_obra_codigos.sql` | policies de `obra_codigos` |
| 0017 | `0017_rls_audit.sql` | policy SELECT de `audit_log` |
| 0018 | `0018_funcoes_negocio.sql` | `criar_obra()`, `resgatar_codigo_obra()` |

> Trigger em `auth.users` (`handle_new_user`): `AFTER INSERT`, `SECURITY DEFINER`, owner `postgres`, `set search_path=''`, corpo com `EXCEPTION WHEN others THEN RETURN new` (NUNCA derrubar o signup) e `INSERT ... ON CONFLICT (id) DO NOTHING` só com `(id, email)` (esqueleto). O backend é dono do conteúdo: logo após Admin API faz UPSERT da profile (`on_conflict_do_update`, sem sobrescrever `created_by`/`created_at`). Ambos idempotentes → ordem irrelevante. Só pode ser criado em contexto privilegiado (o runtime não é dono de `auth.users`; tentar pela app dá 42501).

### 9.2 Performance (obrigatório, já incorporado)
- **Sempre `TO authenticated`** em toda policy (corta avaliação para anon).
- **Envolver chamadas auth em subquery**: `(select auth.uid())`, `(select public.current_obra_ids())` → o planner cacheia via initPlan (ganho documentado de ~99%/100x).
- **Forma correta do filtro**: `obra_id IN (SELECT obra_id FROM obra_membros WHERE profile_id=(select auth.uid()))` — **nunca** a forma correlacionada inversa (`auth.uid() IN (... WHERE obra_membros.obra_id = t.obra_id)`), que força join por linha.
- **Índices que sustentam a RLS**: `obra_membros(profile_id, estado)`, `obra_membros(obra_id)`, e `obra_id` em cada tabela-filha (`audit_log`, `obra_codigos`). Sem eles a RLS vira o gargalo.

### 9.3 Riscos e decisões em aberto
1. **Algoritmo do JWT depende da config do projeto.** Default assimétrico é **RS256**; ES256 é opcional/preferido por performance. **Ação:** confirmar o `alg` real no Dashboard/JWKS e travar `algorithms` de acordo. Não incluir HS256 junto.
2. **`created_by` em `profiles`** referencia `profiles(id)`: o primeiro usuário do sistema (sem criador) tem `created_by = null`. OK.
3. **Gaps em `seq_humano`** por rollback são possíveis (raros) e **aceitáveis** (rótulo, não documento fiscal). Não prometer numeração gapless ao usuário. Se um dia exigir gapless estrito (fiscal), o custo de lock sobe — medir antes.
4. **Enums vs tabela de lookup**: enums nativos são rígidos para renomear/remover. Se os papéis evoluírem muito (ex.: subdivisões de `prestador`), migrar para tabela de domínio. Fase 1: enum.
5. **Imutabilidade do audit_log é contra a aplicação, não contra um superuser/DBA.** Imutabilidade absoluta contra quem tem `postgres`/superuser não é atingível dentro do mesmo banco; se for requisito, prever export WORM externo (fora da Fase 1).
6. **Atomicidade do audit vs falha secundária**: a gravação do log roda na mesma transação da mutação de domínio (consistência). Decidir por tipo de evento se uma falha de log deve abortar a operação de negócio (recomendo abortar para ações críticas como arquivar/aceitar).
7. **`SET LOCAL ROLE authenticated` + `set_config(...,true)`** valem só dentro de transação explícita. Garantir que **toda** rota (inclusive GET puro) abra `session.begin()` — caso contrário `auth.uid()` volta NULL e a RLS nega tudo. Cobrir com teste de fumaça.
8. **Rotação de JWKS**: `PyJWKClient` cacheia o JWK Set (~300s) e refaz fetch se o `kid` não estiver no cache; manter `cache_keys=False`. Prever tolerância a rotação de chave.
9. **Revogação imediata de sessão** (logout antes do `exp`) não é detectada pela validação local; access tokens curtos + refresh. Revogação imediata fica para fase posterior.
10. **Custom domain** muda o `iss` do token — se ativado, reconfirmar `ISSUER`.

---

## Fontes

**RLS / SECURITY DEFINER / performance**
- https://supabase.com/docs/guides/database/postgres/row-level-security
- https://supabase.com/docs/guides/troubleshooting/rls-performance-and-best-practices-Z5Jjwv
- https://www.postgresql.org/docs/current/ddl-rowsecurity.html
- https://github.com/orgs/supabase/discussions/14576
- https://github.com/orgs/supabase/discussions/1138
- https://github.com/orgs/supabase/discussions/30124
- https://dev.to/bairescodeai/infinite-recursion-in-postgres-rls-a-security-definer-gotcha-1916
- https://www.cybertec-postgresql.com/en/abusing-security-definer-functions/
- https://www.postgresql.org/docs/current/sql-createfunction.html
- https://www.bytebase.com/blog/postgres-row-level-security-footguns/
- https://atlasgo.io/guides/orms/sqlalchemy/row-level-security

**Contexto por request / pooler / SQLAlchemy**
- https://github.com/supabase/auth/blob/master/migrations/20211202183645_update_auth_uid.up.sql
- https://github.com/orgs/supabase/discussions/11056
- https://docs.postgrest.org/en/v12/references/auth.html
- https://postgrest.org/en/stable/references/transactions.html
- https://www.adityathebe.com/postgres-parameter-gotcha/
- https://github.com/sqlalchemy/sqlalchemy/discussions/10469
- https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
- https://supabase.com/docs/guides/troubleshooting/supavisor-and-connection-terminology-explained-9pr_ZO
- https://supabase.com/docs/guides/database/connecting-to-postgres

**JWT / signing keys**
- https://supabase.com/docs/guides/auth/jwts
- https://supabase.com/docs/guides/auth/jwt-fields
- https://supabase.com/docs/guides/auth/signing-keys
- https://supabase.com/blog/jwt-signing-keys
- https://pyjwt.readthedocs.io/en/stable/usage.html
- https://pyjwt.readthedocs.io/en/stable/api.html
- https://github.com/jpadilla/pyjwt/issues/1051
- https://github.com/jpadilla/pyjwt/blob/master/jwt/jwks_client.py

**ID sequencial por tenant**
- https://www.postgresql.org/docs/current/functions-sequence.html
- https://www.postgresql.org/docs/current/explicit-locking.html
- https://www.postgresql.org/docs/current/sql-createsequence.html
- https://www.cybertec-postgresql.com/en/gaps-in-sequences-postgresql/
- https://www.postgresql.org/docs/current/sql-insert.html
- https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert
- https://dev.to/oleg_potapov/what-are-postgres-advisory-locks-and-their-use-cases-49nd

**Audit log append-only**
- https://www.postgresql.org/docs/current/sql-revoke.html
- https://www.postgresql.org/docs/current/plpgsql-trigger.html
- https://supabase.com/docs/guides/database/database-advisors?queryGroups=lint&lint=0011_function_search_path_mutable
- https://supabase.com/docs/guides/database/functions
- https://wiki.postgresql.org/wiki/Audit_trigger_91plus
- https://www.cybertec-postgresql.com/en/performance-differences-between-normal-and-generic-audit-triggers/
- https://pydantic.dev/articles/audit-logs-replace-database-triggers

**profiles a partir de auth.users**
- https://supabase.com/docs/guides/auth/managing-user-data
- https://supabase.com/docs/guides/database/postgres/triggers
- https://www.postgresql.org/docs/current/trigger-definition.html
- https://github.com/orgs/supabase/discussions/306
- https://github.com/supabase/supabase/issues/37497
- https://supabase.com/docs/reference/javascript/auth-admin-createuser
