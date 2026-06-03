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


async def obra_member(session: AsyncSession, obra_id: uuid.UUID):
    """Qualquer membro ATIVO da obra (404 se não vê). Retorna (tenant_id, nome, seq_humano, papel).

    Usado por leituras e pelo toggle de item (que admite prestador, não só arquiteto).
    """
    row = (
        await session.execute(
            text(
                """
                select o.tenant_id, o.nome, o.seq_humano, m.papel
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
    return row


async def obra_executor(session: AsyncSession, obra_id: uuid.UUID):
    """Quem EXECUTA a obra: arquiteto OU prestador (cliente é read-only → 403).
    404 se não-membro. Usado por escritas que o prestador também faz (ex.: anexar foto)."""
    row = await obra_member(session, obra_id)
    if row.papel not in ("arquiteto", "prestador"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "cliente não pode executar/anexar nesta obra"
        )
    return row


# ============================ PROJETO (Fase 5) ============================
# NUNCA reusar obra_member/obra_executor p/ projeto: aqueles consultam obra_membros e admitem
# prestador. Projeto é arquiteto↔cliente (prestador não participa).
async def projeto_member(session: AsyncSession, projeto_id: uuid.UUID):
    """Qualquer membro ATIVO do projeto (404 se não vê). Retorna
    (tenant_id, nome, seq_humano, revisoes_incluidas, papel). Usado por leituras e pelos verbos
    do cliente nas revisões."""
    row = (
        await session.execute(
            text(
                """
                select pj.tenant_id, pj.nome, pj.seq_humano, pj.revisoes_incluidas, pm.papel
                from public.projetos pj
                join public.projeto_membros pm
                  on pm.projeto_id = pj.id
                 and pm.profile_id = (select auth.uid())
                 and pm.estado = 'ativo'
                where pj.id = cast(:id as uuid)
                """
            ),
            {"id": str(projeto_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "projeto não encontrado")
    return row


async def projeto_writable(session: AsyncSession, projeto_id: uuid.UUID):
    """Exige arquiteto ATIVO do projeto (404 se não vê; 403 se não é arquiteto)."""
    row = await projeto_member(session, projeto_id)
    if row.papel != "arquiteto":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "apenas o arquiteto pode esta ação")
    return row
