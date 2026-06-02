"""Helpers compartilhados entre os services (contexto de RLS já ativo na sessão)."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def actor_name(session: AsyncSession) -> str | None:
    """Nome do usuário corrente (para o snapshot legível do audit)."""
    row = (
        await session.execute(
            text("select nome from public.profiles where id = (select auth.uid())")
        )
    ).first()
    return row[0] if row else None


async def obra_writable(session: AsyncSession, obra_id: uuid.UUID):
    """Exige que o usuário seja arquiteto ATIVO da obra (404 se não vê; 403 se não é arquiteto)."""
    row = (
        await session.execute(
            text(
                """
                select o.tenant_id, o.nome, o.status, o.seq_humano, m.papel
                from public.obras o
                join public.obra_membros m
                  on m.obra_id = o.id
                 and m.profile_id = (select auth.uid())
                 and m.estado = 'ativo'
                where o.id = cast(:id as uuid)
                """
            ),
            {"id": str(obra_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "obra não encontrada")
    if row.papel != "arquiteto":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "apenas o arquiteto pode esta ação")
    return row
