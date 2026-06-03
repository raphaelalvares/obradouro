"""Serviço de obras. A RLS já escopa os SELECT/UPDATE ao usuário (contexto da sessão);
aqui ficam as regras finas (só arquiteto edita) e a auditoria dos eventos."""

import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problems import limite_from_exc
from app.schemas.obras import ObraCreate
from app.services.audit import log_event
from app.services.common import actor_name, obra_writable

_OBRA_COLS = "id, nome, status, seq_humano, created_at"
# papel do usuário corrente (subquery correlacionada) — só nas LEITURAS (get/list); na criação a
# RPC criar_obra não expõe a tabela obras p/ correlacionar (e o criador é sempre arquiteto).
_MEU_PAPEL = (
    ", (select m.papel from public.obra_membros m "
    "where m.obra_id = obras.id and m.profile_id = (select auth.uid()) "
    "and m.estado = 'ativo') as meu_papel"
)


async def get_obra(session: AsyncSession, obra_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(f"select {_OBRA_COLS}{_MEU_PAPEL} from public.obras where id = cast(:id as uuid)"),
            {"id": str(obra_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "obra não encontrada")
    return dict(row._mapping)


async def list_obras(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            text(f"select {_OBRA_COLS}{_MEU_PAPEL} from public.obras order by seq_humano")
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def create_obra(session: AsyncSession, user_id: str, data: ObraCreate) -> dict:
    try:
        row = (
            await session.execute(
                text(f"select {_OBRA_COLS} from public.criar_obra(cast(:id as uuid), :nome)"),
                {"id": str(data.id), "nome": data.nome},
            )
        ).first()
    except DBAPIError as e:
        err = limite_from_exc(e)  # P0001 'limite_obras_ativas:...' → soft-limit (403)
        if err is not None:
            raise err from e
        raise
    if row is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "não foi possível criar a obra (id em conflito)"
        )
    await log_event(
        session,
        tenant=user_id,
        actor_id=user_id,
        obra_id=data.id,
        action="obra.criada",
        entity_type="obra",
        entity_id=data.id,
        entity_label=row.nome,
        entity_seq=row.seq_humano,
        actor_label=await actor_name(session),
    )
    return dict(row._mapping)


async def rename_obra(session: AsyncSession, user_id: str, obra_id: uuid.UUID, nome: str) -> dict:
    cur = await obra_writable(session, obra_id)
    await session.execute(
        text("update public.obras set nome = :n where id = cast(:id as uuid)"),
        {"n": nome, "id": str(obra_id)},
    )
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="obra.renomeada",
        entity_type="obra",
        entity_id=obra_id,
        changed={"nome": {"de": cur.nome, "para": nome}},
        entity_label=nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return await get_obra(session, obra_id)


async def set_status(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, new_status: str
) -> dict:
    cur = await obra_writable(session, obra_id)
    if cur.status == new_status:
        return await get_obra(session, obra_id)
    if new_status == "ativa":
        # reativar consome vaga → RPC com advisory lock + checagem de limite (pode dar P0001)
        try:
            await session.execute(
                text("select 1 from public.reativar_obra(cast(:id as uuid))"),
                {"id": str(obra_id)},
            )
        except DBAPIError as e:
            err = limite_from_exc(e)
            if err is not None:
                raise err from e
            raise
    else:
        await session.execute(
            text(
                """update public.obras set status = cast(:s as public.status_obra)
                   where id = cast(:id as uuid)"""
            ),
            {"s": new_status, "id": str(obra_id)},
        )
    action = "obra.arquivada" if new_status == "arquivada" else "obra.reativada"
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action=action,
        entity_type="obra",
        entity_id=obra_id,
        changed={"status": {"de": cur.status, "para": new_status}},
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return await get_obra(session, obra_id)


async def list_audit(session: AsyncSession, obra_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                select id, action, entity_type, entity_id, entity_label, entity_seq,
                       actor_label, changed, created_at
                from public.audit_log
                where obra_id = cast(:id as uuid)
                order by created_at desc
                """
            ),
            {"id": str(obra_id)},
        )
    ).all()
    out = []
    for r in rows:
        d = dict(r._mapping)
        if isinstance(d.get("changed"), str):  # asyncpg devolve jsonb como texto
            d["changed"] = json.loads(d["changed"])
        out.append(d)
    return out
