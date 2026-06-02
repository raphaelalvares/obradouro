"""Conexão assíncrona ao Postgres do Supabase (SQLAlchemy + asyncpg) + contexto de RLS por request.

O backend conecta como a role dedicada `cria_app` (NÃO `postgres`/owner), então a RLS é a 2ª
camada de verdade. Cada request roda em UMA transação explícita onde injetamos o contexto do
usuário com `SET LOCAL` (escopo transacional → descartado no commit/rollback → sem vazamento
entre requests que reusam a mesma conexão do pooler).
"""

import json
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

# Supavisor SESSION mode (porta 5432) suporta prepared statements e pool nativo.
engine = create_async_engine(
    settings.DATABASE_URL.get_secret_value(),
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=1800,
    echo=not settings.is_production,
    connect_args={"ssl": True},  # Supabase exige TLS
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


async def get_db(claims: dict) -> AsyncGenerator[AsyncSession, None]:
    """1 request = 1 sessão = 1 transação. A transação explícita é obrigatória inclusive para
    leituras — sem ela o SET LOCAL não vale e auth.uid() volta NULL (RLS nega tudo)."""
    async with SessionLocal() as session:
        async with session.begin():
            await _set_rls_context(session, claims)
            yield session


async def check_db_connection() -> None:
    """Ping de readiness (sem RLS/contexto) — usado pelo health check."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
