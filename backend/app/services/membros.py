"""Serviço de membros da obra: listar e remover. (Convite por email fica em convites.py.)"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit import log_event
from app.services.common import actor_name, obra_writable


async def list_membros(session: AsyncSession, obra_id: uuid.UUID) -> list[dict]:
    """Membros da obra. RLS já restringe a quem é membro ativo da obra."""
    rows = (
        await session.execute(
            text(
                """
                -- B2: contato (email) só p/ arquiteto ativo ou o próprio membro; demais veem null.
                select m.id, m.profile_id, p.nome,
                       case when public.is_arquiteto_ativo(cast(:id as uuid))
                                 or p.id = (select auth.uid())
                            then p.email end as email,
                       m.papel, m.estado, m.created_at
                from public.obra_membros m
                join public.profiles p on p.id = m.profile_id
                where m.obra_id = cast(:id as uuid)
                order by m.created_at
                """
            ),
            {"id": str(obra_id)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def remove_membro(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, membro_id: uuid.UUID
) -> dict:
    cur = await obra_writable(session, obra_id)  # só arquiteto ativo
    target = (
        await session.execute(
            text(
                """
                select m.papel, m.estado, p.nome as membro_nome
                from public.obra_membros m
                join public.profiles p on p.id = m.profile_id
                where m.id = cast(:mid as uuid) and m.obra_id = cast(:oid as uuid)
                """
            ),
            {"mid": str(membro_id), "oid": str(obra_id)},
        )
    ).first()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "membro não encontrado")

    if target.papel == "arquiteto" and target.estado == "ativo":
        n_arq = (
            await session.execute(
                text(
                    """
                    select count(*) from public.obra_membros
                    where obra_id = cast(:oid as uuid) and papel = 'arquiteto' and estado = 'ativo'
                    """
                ),
                {"oid": str(obra_id)},
            )
        ).scalar_one()
        if n_arq <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "não é possível remover o último arquiteto da obra"
            )

    await session.execute(
        text("delete from public.obra_membros where id = cast(:mid as uuid)"),
        {"mid": str(membro_id)},
    )
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="membro.removido",
        entity_type="obra_membro",
        entity_id=membro_id,
        changed={"papel": target.papel},
        entity_label=target.membro_nome or "membro",
        actor_label=await actor_name(session),
    )
    return {"removed": True}
