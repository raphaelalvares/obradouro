"""Dependências compartilhadas das rotas: sessão de DB com contexto de usuário + identidade."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import verify_supabase_jwt


async def db_session(
    claims: Annotated[dict, Depends(verify_supabase_jwt)],
) -> AsyncGenerator[AsyncSession, None]:
    """Sessão de DB já com a RLS escopada ao usuário do JWT."""
    async for session in get_db(claims):
        yield session


def current_user_id(claims: Annotated[dict, Depends(verify_supabase_jwt)]) -> str:
    """profiles.id (= auth.users.id = claim `sub`) do usuário corrente."""
    return claims["sub"]


# Aliases ergonômicos para anotar as rotas.
DbSession = Annotated[AsyncSession, Depends(db_session)]
CurrentUserId = Annotated[str, Depends(current_user_id)]
Claims = Annotated[dict, Depends(verify_supabase_jwt)]
