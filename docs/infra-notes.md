# Infra Notes — Backend CRIA

Guia prático e verificado para configurar o backend (FastAPI + SQLAlchemy async + asyncpg) e o
deploy no EasyPanel/Hostinger, com banco e Auth no Supabase. Arquitetura **API-ONLY** (apps Flutter/React
falam só com a API), backend **persistente** (Docker no EasyPanel, NÃO serverless), RLS como 2ª camada.

Valores marcados com `<...>` você substitui pelo valor real do seu projeto. **Sempre copie a string final
do Dashboard do Supabase** (botão **Connect**), pois região, `project-ref` e prefixo do host do pooler
variam por projeto.

---

## 1) Conexão com o Postgres do Supabase

### Modo recomendado para ESTE caso (VPS Hostinger + EasyPanel/Docker)

**Use o Supavisor em SESSION MODE (Shared Pooler, porta 5432) como conexão principal.**

Motivo decisivo: a **conexão direta** (`db.<ref>.supabase.co`) é **IPv6-only** desde 2024 (a menos que
você pague o add-on IPv4, ~US$4/mês). A doc oficial recomenda a conexão direta para servidores
persistentes — mas isso pressupõe rota IPv6 funcional. Em Docker no Linux o IPv6 vem **desabilitado por
padrão** nos containers, e VPS/EasyPanel geralmente não roteia IPv6 do container sem config extra; logo a
direta tende a falhar com `Network is unreachable`. O **Shared Pooler (Supavisor) é IPv4-only** e funciona
em qualquer ambiente. O **Session mode** mantém uma conexão dedicada por client (comporta-se como conexão
direta), **suporta prepared statements** e é o substituto IPv4 da conexão direta indicado pela própria
Supabase.

**Antes de cravar a direta, teste o IPv6 de saída do container** (de dentro do ambiente do app):

```bash
getent hosts db.<ref>.supabase.co        # deve resolver registro AAAA
python -c "import socket; print(socket.create_connection(('db.<ref>.supabase.co', 5432), 5))"
# ou: curl -6 ifconfig.co   /   ping6 -c1 ipv6.google.com
```

Se o teste IPv6 falhar (timeout / `Network is unreachable`), fique no **Session Pooler (5432)**.
Se passar, a direta na 5432 é levemente mais rápida (sem o hop do Supavisor) e é a recomendação oficial
para persistentes. Habilitar IPv6 no Docker exige configurar o daemon (`ipv6: true` + `fixed-cidr-v6`),
o que o EasyPanel não expõe facilmente — por isso o **caminho de menor atrito é o Session Pooler (5432)**.

### Formato EXATO do DATABASE_URL (SQLAlchemy + asyncpg)

Use **sempre** o prefixo `postgresql+asyncpg://`. O esquema `postgres://` ou `postgresql://` puro faria o
SQLAlchemy escolher o driver **psycopg2 (síncrono)** — o sufixo `+asyncpg` é **obrigatório** para async.
No Session Pooler o usuário inclui o `project-ref` após `postgres.` (com ponto). Faça **URL-encode** da
senha se tiver caracteres especiais (`@`→`%40`, `:`→`%3A`, `/`→`%2F`, espaço→`%20`).

```bash
# RECOMENDADO — Session Pooler (IPv4, porta 5432):
DATABASE_URL=postgresql+asyncpg://postgres.<project-ref>:<SENHA_URLENCODED>@aws-<region>.pooler.supabase.com:5432/postgres

# ALTERNATIVA — Direta (só se o container tiver IPv6 de saída comprovado):
DATABASE_URL=postgresql+asyncpg://postgres:<SENHA_URLENCODED>@db.<project-ref>.supabase.co:5432/postgres
```

> Observação: o `.env.example` do repo traz um placeholder genérico
> (`postgresql+asyncpg://postgres:SENHA@HOST:5432/postgres`). Substitua pelo Session Pooler acima
> (note o usuário `postgres.<ref>` e o host `aws-<region>.pooler.supabase.com`).

### Referência rápida de hostnames/portas (2025/2026)

| Alvo | Host | Porta | Usuário | Rede | Quando usar |
|---|---|---|---|---|---|
| Session Pooler | `aws-<region>.pooler.supabase.com` | **5432** | `postgres.<ref>` | IPv4 | **Runtime da API (recomendado)**, migrations, pg_dump |
| Direta | `db.<ref>.supabase.co` | 5432 | `postgres` | IPv6 (IPv4 = add-on pago) | Persistente COM IPv6; migrations |
| Transaction Pooler | `aws-<region>.pooler.supabase.com` | 6543 | `postgres.<ref>` | IPv4 | Serverless/edge efêmero (evitar aqui) |

Banco padrão sempre `postgres`. Desde fev/2025: **6543 é só transaction, 5432 é só session.**

### Configuração do engine — Session mode (5432)

Em session mode cada conexão é dedicada ao client, então você **pode e deve** usar o pool nativo do
SQLAlchemy, e **prepared statements funcionam** (não precisa desligar statement cache).

```python
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={"ssl": True},   # Supabase exige TLS
)
```

**SSL/TLS com asyncpg:** Supabase exige TLS. Parâmetros estilo libpq (`?sslmode=require` na URL) **não**
são interpretados pelo asyncpg do mesmo jeito que pelo psycopg — passe `ssl` via `connect_args`. O mais
simples é `{"ssl": True}` (usa contexto TLS padrão). Para verificação estrita da cadeia, baixe o CA em
**Dashboard > Settings > Database > SSL Configuration** e use
`ssl=ssl.create_default_context(cafile="prod-ca-2021.crt")`.

**Limite de conexões:** o Shared Pooler tem teto por projeto (tipicamente ~15 por modo no plano Free,
configurável em **Dashboard > Database > Connection pooling**). Some `pool_size + max_overflow` de **todas
as réplicas/containers** e mantenha abaixo do teto.

### Transaction mode (6543) — quando NÃO usar

O Transaction Mode (6543) é otimizado para serverless/edge com conexões transientes — **não** é ideal para
um backend persistente que mantém o próprio pool. Ele **não suporta prepared statements** (compartilha a
conexão física entre clients), então com asyncpg você toma `DuplicatePreparedStatementError`. Se for
**obrigado** a usar 6543, a config canônica robusta é:

```python
from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

engine = create_async_engine(
    "postgresql+asyncpg://postgres.<ref>:<senha>@aws-<region>.pooler.supabase.com:6543/postgres",
    poolclass=NullPool,  # o Supavisor já faz o pooling; evita pool duplo
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",  # statements com nome único
        "ssl": True,
    },
)
```

> Relatos em issues da Supabase mostram que **só** `statement_cache_size=0` às vezes **não** elimina o
> erro com SQLAlchemy; o `prepared_statement_name_func` é o que fecha o caso. Desligar prepared statements
> degrada performance — mais um motivo para preferir **session mode (5432)** neste backend.

**Fontes:**
- https://supabase.com/docs/guides/database/connecting-to-postgres
- https://supabase.com/docs/guides/platform/ipv4-address
- https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.asyncpg
- https://magicstack.github.io/asyncpg/current/api/index.html
- https://supabase.com/docs/guides/troubleshooting/supavisor-faq-YyP5tI
- https://github.com/sqlalchemy/sqlalchemy/discussions/10246
- https://github.com/orgs/supabase/discussions/36618
- https://www.hostinger.com/support/8703798-how-to-use-the-easypanel-vps-template-at-hostinger/

---

## 2) supabase-py admin (criar usuário, gerar link de convite/senha, redirect/deep link)

> Este client de Auth/Admin (supabase-py) é **separado** do acesso a dados via SQLAlchemy/asyncpg.
> Ele serve só para chamadas **administrativas de Auth** (criar usuário, gerar link).

### Versão do pacote (verificado 2026-06-02)

O `requirements.txt` do repo fixa `supabase>=2.10,<3.0`, o que é compatível. A versão estável mais recente
no PyPI é **`supabase==2.30.1`** (lançada 2026-05-29; o único tag mais novo no GitHub é o alpha `v3.0.0a1`).
Para builds Docker reprodutíveis, **recomenda-se fixar exato**: `supabase==2.30.1`. Esse pacote traz, todos
pinados na mesma versão, `supabase-auth==2.30.1` (sucessor do antigo `gotrue-py`, onde vivem
`create_user`/`generate_link`/`invite_user_by_email`), `postgrest`, `storage3`, `realtime` e
`supabase-functions`. `requires_python >= 3.9` (Python 3.12 OK) e `httpx >=0.26,<0.29`. **Não misture**
versões fora do conjunto pinado.

```python
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions   # caminho válido
# (a doc atual também sugere: from supabase.client import ClientOptions)
```

### Criar o client com a service role / secret key (server-side)

Para uso administrativo, desligue `auto_refresh_token` e `persist_session` (é um client sem sessão de
usuário). Qualquer método sob `supabase.auth.admin` **exige a chave secreta** (service_role / `sb_secret_`).
Em FastAPI async, **prefira o client async** (`acreate_client` / `create_async_client`) — o `create_client`
síncrono **bloqueia o event loop**.

```python
import os
from supabase import acreate_client
from supabase.lib.client_options import ClientOptions

supabase = await acreate_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    options=ClientOptions(auto_refresh_token=False, persist_session=False),
)
admin = supabase.auth.admin   # métodos viram await: await admin.create_user(...)
```

### Nomenclatura de chaves: `sb_secret_` (novo) vs `service_role` (legado)

Desde jun/2025 a Supabase introduziu `sb_publishable_...` (substitui `anon`, pode ir no app) e
`sb_secret_...` (substitui `service_role`, **só no servidor**, revogável/rotacionável/auditável). As JWTs
legadas continuam válidas na transição (deleção prevista para fins de 2026). **Recomendado adotar
`sb_secret_`** para o backend. Ambas funcionam hoje como segundo argumento do `create_client`.

```bash
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sb_secret_xxxxx   # ou a JWT legada eyJ... ; SÓ no backend
# Para o front web (se necessário): sb_publishable_xxxxx / anon — NUNCA a secret.
```

> Como a arquitetura é **API-ONLY**, idealmente nem distribua chave Supabase nos apps Flutter/React (eles
> falam só com a sua API). A secret fica **exclusivamente no backend**.

### `create_user` — criar usuário (opcionalmente já confirmado)

Recebe **um dict** (`AdminUserAttributes`, campos opcionais): `email`, `phone`, `password`,
`email_confirm` (bool, default **False**), `phone_confirm`, `user_metadata`, `app_metadata`,
`ban_duration`, `role`, `id`, etc. **Não envia e-mail.** Para já criar **confirmado**, passe
`email_confirm=True`.

```python
resp = await supabase.auth.admin.create_user({
    "email": "user@email.com",
    "password": "senha-segura",
    "email_confirm": True,
    "user_metadata": {"name": "Fulano"},
})
# resp.user contém o usuário criado
```

### `generate_link` — gera o link (NÃO envia e-mail) com `redirect_to`

Recebe `GenerateLinkParams`: `type`, `email` e (conforme o tipo) `password`/`new_email`, mais um
**`options` aninhado** com `redirect_to` e `data`. **Importante: `redirect_to` vai DENTRO de `options`**,
não na raiz. Tipos: `signup`, `invite`, `magiclink`, `recovery`, `email_change_current`,
`email_change_new`. Retorna o link em `resp.properties.action_link` (ideal para e-mail customizado/deep
link mobile). Para `signup`, `password` é obrigatório e o usuário é criado pela chamada.

```python
# DEFINIR senha de usuário NOVO -> type="invite" (cria o usuário se não existir):
resp = await supabase.auth.admin.generate_link({
    "type": "invite",
    "email": "user@email.com",
    "options": {"redirect_to": "https://app.criaweb.com.br/definir-senha"},
})

# REDEFINIR senha de usuário existente -> type="recovery":
resp = await supabase.auth.admin.generate_link({
    "type": "recovery",
    "email": "user@email.com",
    "options": {"redirect_to": "com.goidea.cria://auth-callback"},
})
link = resp.properties.action_link
```

### `invite_user_by_email` — convite que JÁ envia o e-mail

Cria o usuário **e** dispara o e-mail de convite usando o template de Auth do projeto. Use quando quiser
que a própria Supabase mande o e-mail.

```python
resp = await supabase.auth.admin.invite_user_by_email(
    "user@email.com",
    {"redirect_to": "https://app.criaweb.com.br/definir-senha", "data": {"role": "membro"}},
)
```

> Depende do **SMTP do projeto** estar configurado. O SMTP default da Supabase tem rate limit baixo (só
> dev) — para produção, configure SMTP próprio. Para controle total do e-mail (branding/deep link mobile),
> prefira `create_user` + `generate_link` e envie você mesmo.

### `redirect_to`: deep link mobile (esquema custom) + URL web

Adicione **todas** as URLs em **Authentication > URL Configuration**. Se o `redirect_to` não casar com uma
entrada permitida, cai no **Site URL**. Wildcards glob suportados: `*` (não atravessa `.` nem `/`), `**`
(qualquer sequência), `?`.

```text
Mobile (custom scheme): com.goidea.cria://auth-callback
Web prod:               https://app.criaweb.com.br/auth/callback
Web allowlist (glob):   https://app.criaweb.com.br/**
Vercel previews:        https://*-<seu-slug>.vercel.app/**
Local dev (só em dev):  http://localhost:3000/**
```

> O esquema custom (`com.goidea.cria://`) precisa estar registrado no app Flutter (iOS
> `CFBundleURLSchemes` / Android `intent-filter`). Nunca deixe `localhost` na allowlist de produção.

### Segurança (a secret IGNORA RLS)

Todo método `auth.admin` exige a secret e **bypassa RLS** — rode só no backend confiável. Nunca exponha a
secret no browser, apps, repositório ou logs (use env var no EasyPanel marcada como secret). Como a secret
ignora RLS, **as rotas admin não são protegidas pela 2ª camada** — implemente checagem de papel/permissão
no FastAPI **antes** de qualquer chamada admin.

**Fontes:**
- https://pypi.org/pypi/supabase/json
- https://supabase.com/docs/reference/python/initializing
- https://supabase.com/docs/reference/python/admin-api
- https://supabase.com/docs/reference/python/auth-admin-createuser
- https://supabase.com/docs/reference/python/auth-admin-generatelink
- https://supabase.com/docs/reference/python/auth-admin-inviteuserbyemail
- https://github.com/supabase/auth-py/blob/main/supabase_auth/_async/gotrue_admin_api.py
- https://supabase.com/docs/guides/auth/redirect-urls
- https://supabase.com/docs/guides/api/api-keys
- https://github.com/orgs/supabase/discussions/29260

---

## 3) Deploy no EasyPanel (Hostinger VPS)

EasyPanel = Docker + Traefik. Como o Postgres roda no Supabase (fora da VPS), você **não** reserva RAM para
banco na VPS.

### Dimensionamento da VPS (Hostinger KVM)

Piso confortável para FastAPI persistente + EasyPanel/Traefik: **KVM 2 (2 vCPU / 8 GB)**. O KVM 1
(1 vCPU / 4 GB) funciona, mas EasyPanel/Docker/Traefik já consomem ~1–1.5 GB. Suba para KVM 4 ao adicionar
Redis/filas/observabilidade. Hostinger é KVM (virtualização real), NVMe, root completo. Preços
promocionais (renovação mais cara) — confirme no painel na hora.

| Plano | vCPU / RAM / Disco | Indicação |
|---|---|---|
| KVM 1 | 1 / 4 GB / 50 GB NVMe | mínimo, aperta rápido |
| **KVM 2** | 2 / 8 GB / 100 GB NVMe | **produção inicial (recomendado)** |
| KVM 4 | 4 / 16 GB / 200 GB NVMe | + Redis/filas/observabilidade |

### Criar o App a partir de Git/Dockerfile (monorepo /backend)

Crie um serviço do tipo **App**. Em **Source**, escolha GitHub + branch (ex.: `main`). Em **Build**, escolha
**Dockerfile** e preencha o campo **File** com o caminho relativo à raiz do repo: **`backend/Dockerfile`**.

> Atenção monorepo: o **contexto de build é a raiz do repo**, e o EasyPanel não expõe campo separado de
> "build context" para subpasta. O `Dockerfile` atual do repo está escrito com `COPY requirements.txt` /
> `COPY app ./app` (caminhos relativos a `backend/`). Para o build a partir da raiz funcionar, ou ajuste os
> `COPY` para `COPY backend/requirements.txt` / `COPY backend/app ./app`, **ou** valide se a sua versão do
> EasyPanel permite definir o contexto como `/backend`. Alinhe isso antes do primeiro deploy.

Ative **Auto Deploy** (cria webhook no GitHub e faz deploy on-push). Magic vars disponíveis:
`$(PROJECT_NAME)`, `$(SERVICE_NAME)`, `$(PRIMARY_DOMAIN)`.

### Porta de proxy, domínio e SSL

- **Proxy Port = 8000** — deve ser **idêntica** à `--port` do CMD do container (o `Dockerfile` do repo usa
  `uvicorn ... --port 8000`). Divergência causa 502.
- O container deve escutar em **`0.0.0.0`** (não `127.0.0.1`), o que o CMD já faz.
- **Domains:** adicione o domínio; ative o toggle de **SSL/Let's Encrypt** (certificado automático em
  segundos). **Aponte o DNS (A/AAAA) para o IP da VPS antes** — o certificado só é emitido após o DNS
  resolver para o IP.
- Como Traefik faz a terminação TLS, o app roda HTTP puro na porta interna; rode o uvicorn com
  **`--proxy-headers`** para receber IP/protocolo corretos do cliente. (Ajuste recomendado no CMD do
  `Dockerfile`: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers`.)

### Variáveis de ambiente / segredos

Coloque tudo na seção **Environment** do serviço App (disponível em build-time **e** run-time). **Não**
commite `.env` com segredos — use o `.env.example` (sem valores) como referência e injete os reais no painel.

```bash
ENVIRONMENT=production
DATABASE_URL=postgresql+asyncpg://postgres.<ref>:<SENHA_URLENCODED>@aws-<region>.pooler.supabase.com:5432/postgres
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sb_secret_xxxxx     # marcar como secret/oculto
SUPABASE_ANON_KEY=sb_publishable_xxxxx        # opcional
CORS_ORIGINS=https://app.criaweb.com.br
```

> Como as variáveis também existem em build-time, evite usar segredos durante o `docker build` (não devem
> acabar em camadas da imagem). Para arquivos de config, use **Mount** do tipo **File**.

### Health check e réplicas

A doc oficial do App service **não** expõe um health check HTTP nativo (path/intervalo) configurável no
painel — o roteamento do Traefik valida a porta. O projeto já cobre isso de duas formas:

- **Endpoint da API:** `GET /api/v1/health` (já existe no app — confirme em `app/main.py`).
- **`HEALTHCHECK` no Dockerfile** (já presente): bate em `http://127.0.0.1:8000/api/v1/health`.
- **Monitor externo opcional:** template self-host **Gatus** apontando para
  `https://<seu-domínio>/api/v1/health`.

Em **Deploy**, defina **Replicas = 1** no início e suba conforme a carga. Workers do uvicorn ~ nº de vCPU
(comece com `workers = nº de vCPU` e meça; se usar `--workers`, lembre do teto de conexões do pooler somando
todas as réplicas × workers).

**Fontes:**
- https://easypanel.io/docs/services/app
- https://easypanel.io/docs/builders
- https://easypanel.io/docs/guides/custom-ssl
- https://easypanel.io/docs/templates/gatus
- https://fastapi.tiangolo.com/deployment/docker/
- https://www.hostinger.com/vps-hosting
- https://www.hostinger.com/pricing/vps-hosting

---

## 4) Migrations (assistente gera o SQL, usuário aplica)

Arquivos SQL ficam em **`/supabase/migrations`**, versionados no git. **Decisão do projeto:** o assistente
**gera** o `.sql`, o usuário **aplica** no Supabase.

### Convenção de nome e timestamp

Nome: **`YYYYMMDDHHmmss_<descricao>.sql`** — aplicados em **ordem de timestamp** (= ordem de aplicação).
Para evitar erro humano de timestamp, prefira gerar o arquivo vazio com o CLI e deixar o assistente
preencher o SQL:

```bash
supabase migration new create_profiles_table
# -> supabase/migrations/20260602093000_create_profiles_table.sql
```

> Se o timestamp for escolhido à mão, ele deve ser **estritamente crescente** vs. as migrations já
> aplicadas; menor/duplicado quebra o histórico.

Setup do CLI (uma vez, na raiz do monorepo). No Windows use **Scoop** (não há `npm install -g supabase`),
ou rode via `npx` (Node 20+):

```bash
scoop bucket add supabase https://github.com/supabase/scoop-bucket.git ; scoop install supabase
supabase init        # cria supabase/config.toml, supabase/migrations/, supabase/seed.sql
```

### Aplicar: SQL Editor (colar) vs `supabase db push`

Duas formas oficiais — **escolha um caminho por ambiente** e seja consistente:

- **(A) SQL Editor do Dashboard** — cole o conteúdo do `.sql`. Simples, sem CLI, bom para começar.
- **(B) Versionado (recomendado):** `supabase link --project-ref <ref>` + `supabase db push` (aplica os
  arquivos ainda não registrados no remoto).

```bash
supabase login
supabase link --project-ref <project-ref>
supabase db push --dry-run     # prévia
supabase db push               # aplica
supabase migration list        # status
```

> `db push` registra cada migration em `supabase_migrations.schema_migrations` e **pula** as já aplicadas.
> **Armadilha:** se você aplicou via SQL Editor, o `push` **não sabe** e tentará reaplicar → use
> `supabase migration repair` para reconciliar. Nunca altere o banco remoto fora desse fluxo.

**Conexão para aplicar migrations:** use **porta 5432** (Session pooler ou direta). **NUNCA 6543**
(transaction pooler) — DDL e estado de sessão quebram lá. Via CLI, o normal é `db push` com a senha do DB
(`-p <DB_PASSWORD>` ou env `SUPABASE_DB_PASSWORD`); a flag `--db-url` só é necessária para self-hosted.

### RLS (API-ONLY, RLS como 2ª camada)

**Em TODA migration que cria tabela, habilite RLS na MESMA migration** — tabelas criadas via SQL/migration
**não** têm RLS por padrão (só as criadas pela UI do Dashboard têm). Versione cada `CREATE POLICY` e os
`GRANT`s no arquivo. Para performance, envolva `auth.uid()` em `(select auth.uid())`, direcione policies com
`TO authenticated/anon`, e crie índice na coluna usada na policy.

```sql
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users select own" ON public.profiles
  FOR SELECT TO authenticated USING ((select auth.uid()) = user_id);

CREATE POLICY "Users insert own" ON public.profiles
  FOR INSERT TO authenticated WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Users update own" ON public.profiles
  FOR UPDATE TO authenticated
  USING ((select auth.uid()) = user_id)
  WITH CHECK ((select auth.uid()) = user_id);

CREATE INDEX IF NOT EXISTS idx_profiles_user_id ON public.profiles (user_id);
```

> **ATENÇÃO crítica:** a RLS só vale para as roles `anon`/`authenticated`. Se a sua API FastAPI conecta com
> a role **`postgres`** (owner) via asyncpg — que é o usuário das connection strings acima — ela faz
> **BYPASS de RLS**. Ou seja, a 2ª camada **não** protege o caminho da API a menos que você conecte com uma
> role não-privilegiada dedicada (ou use `SET ROLE` / `SET request.jwt.claims`). Se quiser RLS valendo
> também na API, crie uma role de aplicação dedicada.

### DEV e PROD (dois projetos Supabase)

**Uma** pasta `supabase/migrations` versionada serve aos dois projetos. Promova as **mesmas** migrations
trocando o `project-ref` no link:

```bash
# DEV
supabase link --project-ref <DEV_REF>  && supabase db push
# PROD
supabase link --project-ref <PROD_REF> && supabase db push
```

Padrão CI: `develop -> projeto DEV`, `main -> projeto PROD` via GitHub Actions
(secrets: `SUPABASE_ACCESS_TOKEN`, `*_PROJECT_ID`, `*_DB_PASSWORD`). Cada projeto tem seu próprio
`schema_migrations` — aplique na **mesma ordem** nos dois e não edite prod fora das migrations. O
`project-ref` vem da URL `https://supabase.com/dashboard/project/<project-id>`.

**Fontes:**
- https://supabase.com/docs/guides/deployment/database-migrations
- https://supabase.com/docs/reference/cli/supabase-migration-new
- https://supabase.com/docs/reference/cli/supabase-db-push
- https://supabase.com/docs/guides/database/postgres/row-level-security
- https://supabase.com/docs/guides/troubleshooting/rls-performance-and-best-practices-Z5Jjwv
- https://supabase.com/docs/guides/api/securing-your-api
- https://supabase.com/docs/guides/deployment/managing-environments
- https://supabase.com/docs/guides/local-development/cli/getting-started

---

## 5) Backups (rotina desde o dia 1)

### Arquitetura: o que precisa de backup

O banco vive no **Supabase**; a API roda no **EasyPanel/Hostinger**. São **duas camadas separadas**:

- **Camada 1 (dados/DB):** backups do Supabase + seu `pg_dump` lógico **offsite**.
- **Camada 2 (VPS/app):** snapshots/backups da Hostinger + código no git + secrets fora do repo.

> O Postgres **não** está na VPS: o snapshot da Hostinger **não** salva o banco. E o recurso "Database
> Backups" nativo do EasyPanel só faz backup de bancos **hospedados dentro do EasyPanel** — **não** se
> aplica ao seu DB principal (que é o Supabase).

### Supabase: backups gerenciados por plano

- **Daily backups automáticos:** só em **Pro (7 dias)**, **Team (14 dias)**, **Enterprise (até 30 dias)**.
  O **Free tier não tem** backups gerenciados — só `pg_dump` manual.
- Para o CRIA em produção, assuma **plano Pro como mínimo** (7 dias de daily).
- Daily backups **não armazenam senhas de custom roles** — após restaurar, resete essas senhas.
- **PITR** (add-on pago, Pro/Team/Enterprise): restaura a qualquer ponto, RPO padrão ~2 min (WAL a cada
  2 min); retenção 7/14/28 dias; requer compute ≥ Small. **Habilitar PITR desativa os daily backups.** Só
  vale se RPO de 24h (daily) for inaceitável.

### Supabase: backup lógico portável via CLI (recomendado dia 1)

Independente do plano, gere dumps lógicos para **portabilidade** (sair do Supabase / restaurar em qualquer
Postgres). Três arquivos separados — o default é **schema-only**; sem `--data-only` você **não** captura os
dados:

```bash
supabase db dump --db-url "$DB_URL" -f roles.sql  --role-only
supabase db dump --db-url "$DB_URL" -f schema.sql
supabase db dump --db-url "$DB_URL" -f data.sql   --use-copy --data-only \
  -x "storage.buckets_vectors" -x "storage.vector_indexes"
```

Restore (roles → schema → dados, em transação única, com triggers/RLS desativados na carga):

```bash
psql --single-transaction --variable ON_ERROR_STOP=1 \
  --file roles.sql --file schema.sql \
  --command 'SET session_replication_role = replica' \
  --file data.sql --dbname "$TARGET_CONNECTION_STRING"
```

**Conexão para dump/backup:** **porta 5432** (Session pooler ou direta), **NUNCA 6543** — dump precisa de
sessão estável. `--db-url` deve ter a senha **percent-encoded**.

```bash
# Session pooler (IPv4, ideal em CI/VPS sem IPv6):
DB_URL=postgresql://postgres.<ref>:<SENHA_URLENCODED>@aws-<region>.pooler.supabase.com:5432/postgres
```

> **Armadilha de versão:** `pg_dump` recusa servidor com major **maior** que o cliente
> (`aborting because of server version mismatch`). Prefira `supabase db dump` (roda `pg_dump` em container,
> alinhando a versão); se usar `pg_dump` local, fixe a versão ≥ a do Postgres do projeto.

### Automatizar o `pg_dump` do Supabase a partir da VPS

Template 1-click **`postgres-backup-s3`** (imagem `easypanel/postgres-backup-s3`) no EasyPanel: roda
`pg_dump` agendado e envia para S3-compatível (S3, Backblaze, DigitalOcean Spaces, MinIO, Storj). Aponte
Host/User/Password para a connection string do Supabase **na porta 5432**.

```text
Postgres Host/Port(5432)/User/Password -> Supabase (5432, nunca 6543)
S3 Access Key / Secret Key / Bucket / Region / Endpoint / Prefix
Schedule (CRON): 0 3 * * *
```

> Mesma armadilha de versão do `pg_dump` embutido na imagem vs. Postgres do Supabase. Alternativa: GitHub
> Actions agendado (cron) gerando `roles.sql + schema.sql + data.sql` versionados por data.

### Hostinger VPS: snapshots e backups

- **Semanal:** automático e gratuito em todos os planos. **Diário:** upgrade pago.
- Retenção: até **4 no total** (2 diários + 2 semanais); cada novo substitui o mais antigo do mesmo tipo.
- **Snapshot:** manual, 1 por vez (novo sobrescreve), auto-delete em 20 dias.
- Caminho: **hPanel > VPS > Manage > Backups & Monitoring > Snapshots & Backups**.
- **Restore sobrescreve TODA a VPS** e não pode ser interrompido; não dá para baixar backups para a máquina
  local.

### Rotina prática recomendada (dia 1)

1. **Supabase Pro** → daily backups 7d (automático). Avalie **PITR 7d** se RPO de 24h não bastar.
2. **`pg_dump` lógico** diário/3x semana → storage externo (template `postgres-backup-s3` ou GitHub Actions
   cron `0 3 * * *`), gerando `roles.sql + schema.sql + data.sql` datados.
3. **Código** no git (fonte da verdade); `.env`/secrets **fora** do repo e copiados num cofre.
4. **Hostinger:** manter backup semanal (grátis) + **snapshot manual antes de cada deploy** grande.
5. **Mensalmente:** testar restore do dump lógico num projeto Supabase descartável. Regra **3-2-1**
   (3 cópias, 2 mídias, 1 offsite).

> Backups gerenciados do Supabase ficam **dentro** do Supabase — o `pg_dump` lógico offsite é o que garante
> portabilidade e protege contra perda/bloqueio da conta. **Backup não testado não é backup.** Guarde as
> senhas de custom roles separadamente (daily backups não as guardam).

**Fontes:**
- https://supabase.com/docs/guides/platform/backups
- https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore
- https://supabase.com/docs/reference/cli/supabase-db-dump
- https://supabase.com/docs/guides/database/connecting-to-postgres
- https://easypanel.io/docs/database-backups
- https://easypanel.io/docs/templates/postgres-backup
- https://www.hostinger.com/support/1583232-how-to-back-up-or-restore-a-vps-at-hostinger/
