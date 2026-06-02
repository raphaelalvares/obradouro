"""Serviço de convites: por email (Admin API), aceitar e listar pendentes."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.audit import log_event
from app.services.common import actor_name, obra_writable
from app.services.users import invite_or_attach


async def convidar_por_email(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, email: str, papel: str
) -> dict:
    cur = await obra_writable(session, obra_id)  # só arquiteto ativo convida
    settings = get_settings()
    invitee_id, action_link, _created = await invite_or_attach(email, settings.INVITE_REDIRECT_URL)
    # Cria o vínculo pendente. A profile do convidado já existe (trigger handle_new_user no
    # signup / Admin API). RLS de INSERT permite porque o ator é arquiteto ativo da obra.
    res = (
        await session.execute(
            text(
                """
                insert into public.obra_membros (obra_id, profile_id, papel, estado, invited_by)
                values (cast(:oid as uuid), cast(:pid as uuid),
                        cast(:papel as public.papel_obra), 'pendente', (select auth.uid()))
                on conflict (obra_id, profile_id) do nothing
                returning estado
                """
            ),
            {"oid": str(obra_id), "pid": str(invitee_id), "papel": papel},
        )
    ).first()
    if res is None:
        # já era membro/convidado: não reenvia nem re-audita; devolve o estado atual
        atual = (
            await session.execute(
                text(
                    """select estado from public.obra_membros
                       where obra_id = cast(:oid as uuid) and profile_id = cast(:pid as uuid)"""
                ),
                {"oid": str(obra_id), "pid": str(invitee_id)},
            )
        ).first()
        return {
            "profile_id": invitee_id,
            "estado": atual.estado if atual else "pendente",
            "action_link": None,
        }
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="convite.enviado",
        entity_type="obra",
        entity_id=obra_id,
        changed={"email": email, "papel": papel},
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return {"profile_id": invitee_id, "estado": "pendente", "action_link": action_link}


async def aceitar_convite(session: AsyncSession, user_id: str, membro_id: uuid.UUID) -> dict:
    res = (
        await session.execute(
            text(
                """update public.obra_membros set estado = 'ativo'
                   where id = cast(:mid as uuid)
                     and profile_id = (select auth.uid())
                     and estado = 'pendente'
                   returning obra_id"""
            ),
            {"mid": str(membro_id)},
        )
    ).first()
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "convite pendente não encontrado")
    obra_id = res.obra_id
    # Agora o usuário é ativo → a RLS já o deixa ler a obra (mudança visível na transação).
    obra = (
        await session.execute(
            text(
                "select tenant_id, nome, seq_humano from public.obras where id = cast(:oid as uuid)"
            ),
            {"oid": str(obra_id)},
        )
    ).first()
    await log_event(
        session,
        tenant=obra.tenant_id if obra else user_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="convite.aceito",
        entity_type="obra",
        entity_id=obra_id,
        entity_label=obra.nome if obra else "obra",
        entity_seq=obra.seq_humano if obra else None,
        actor_label=await actor_name(session),
    )
    return {"obra_id": obra_id, "estado": "ativo"}


async def listar_pendentes(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """select obra_id, obra_nome, seq_humano, invited_by_nome
                   from public.minhas_obras_pendentes()"""
            )
        )
    ).all()
    return [dict(r._mapping) for r in rows]
