"""Conexão assíncrona ao Postgres do Supabase (SQLAlchemy + asyncpg) + contexto de RLS por request.

O backend conecta como a role dedicada `cria_app` (NÃO `postgres`/owner), então a RLS é a 2ª
camada de verdade. Cada request roda em UMA transação explícita onde injetamos o contexto do
usuário com `SET LOCAL` (escopo transacional → descartado no commit/rollback → sem vazamento
entre requests que reusam a mesma conexão do pooler).
"""

import json
import ssl
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()


def _ssl_arg() -> ssl.SSLContext | bool:
    """SSL p/ o asyncpg, em 3 modos:
    - DB_SSL_INSECURE=true (DEV): contexto SEM verificação — o pooler do Supabase apresenta CA
      própria e, sem o cert dessa CA, o verify estrito falha (ex.: Windows). NUNCA em produção.
    - DB_SSL_ROOT_CERT setado (PRODUÇÃO): verify-full contra a CA do Supabase (cadeia + hostname).
    - default: ssl=True (verifica contra o trust store do SO)."""
    if settings.DB_SSL_INSECURE:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    if settings.DB_SSL_ROOT_CERT:
        return ssl.create_default_context(cafile=settings.DB_SSL_ROOT_CERT)
    return True


# Supavisor SESSION mode (porta 5432) suporta prepared statements e pool nativo.
engine = create_async_engine(
    settings.DATABASE_URL.get_secret_value(),
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=1800,
    echo=settings.SQL_ECHO,  # explícito (não vaza params por inércia de ENVIRONMENT)
    connect_args={"ssl": _ssl_arg()},  # Supabase exige TLS
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _set_rls_context(session: AsyncSession, claims: dict) -> None:
    """Injeta o usuário atual na sessão. SET LOCAL = transacional (sem vazamento no pool)."""
    minimal = json.dumps(
        {"sub": claims["sub"], "role": "authenticated", "email": claims.get("email")}
    )
    await session.execute(text("SET LOCAL ROLE authenticated"))
    # set_config(..., true) == SET LOCAL; bind param SEMPRE (nunca interpolar string)
    await session.execute(text("SELECT set_config('request.jwt.claims', :c, true)"), {"c": minimal})


@asynccontextmanager
async def db_context(claims: dict) -> AsyncGenerator[AsyncSession, None]:
    """1 sessão = 1 transação, já com a RLS escopada ao usuário do JWT. A transação explícita é
    obrigatória inclusive para leituras — sem ela o SET LOCAL não vale e auth.uid() volta NULL
    (RLS nega tudo).

    Use diretamente (`async with db_context(claims) as session:`) quando precisar abrir a conexão
    do banco TARDE — depois de um trabalho pesado fora da transação (ler upload + processar imagem),
    para NÃO segurar uma conexão do pool durante o processamento. O fluxo normal de request usa o
    `get_db` (dependency) abaixo, que delega aqui."""
    async with SessionLocal() as session:
        async with session.begin():
            await _set_rls_context(session, claims)
            yield session


async def get_db(claims: dict) -> AsyncGenerator[AsyncSession, None]:
    """1 request = 1 sessão = 1 transação (via `db_context`). Usado como dependency das rotas."""
    async with db_context(claims) as session:
        yield session


async def check_db_connection() -> None:
    """Ping de readiness (sem RLS/contexto) — usado pelo health check."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def assert_safe_db_role() -> None:
    """Salvaguarda de boot: a RLS (2ª camada) só vale se o backend NÃO conectar como
    superuser nem com BYPASSRLS. Falha o startup em produção se a role for insegura."""
    import logging

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    """
                    select current_user as usr,
                           current_setting('is_superuser') as superuser,
                           coalesce(
                               (select rolbypassrls from pg_roles where rolname = current_user),
                               false) as bypassrls
                    """
                )
            )
        ).first()
    if row.superuser == "on" or row.bypassrls:
        msg = (
            f"Role de DB insegura p/ RLS: user={row.usr} superuser={row.superuser} "
            f"bypassrls={row.bypassrls}. Conecte como 'cria_app' (não-owner)."
        )
        if get_settings().is_production:
            raise RuntimeError(msg)
        logging.getLogger("cria").warning(msg)
