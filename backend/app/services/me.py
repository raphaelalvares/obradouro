"""Serviço do perfil do usuário corrente. Usa auth.uid() (contexto de RLS da sessão)."""

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.me import ProfileUpdate

_SELECT_ME = "select id, email, nome, telefone from public.profiles where id = (select auth.uid())"


async def get_me(session: AsyncSession) -> dict:
    row = (await session.execute(text(_SELECT_ME))).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "perfil não encontrado")
    return dict(row._mapping)


async def get_or_create_me(session: AsyncSession, email: str | None) -> dict:
    """Cria a própria profile se faltar (rede de segurança além do trigger handle_new_user)."""
    await session.execute(
        text(
            """insert into public.profiles (id, email)
               values ((select auth.uid()), :email)
               on conflict (id) do nothing"""
        ),
        {"email": email},
    )
    return await get_me(session)


async def update_me(session: AsyncSession, email: str | None, data: ProfileUpdate) -> dict:
    await get_or_create_me(session, email)  # garante a profile (consistente com GET /me)
    fields = data.model_dump(exclude_unset=True)
    if fields:
        # chaves vêm de campos fixos do schema (nome/telefone); valores são bind params
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        await session.execute(
            text(f"update public.profiles set {sets} where id = (select auth.uid())"),
            fields,
        )
    return await get_me(session)
