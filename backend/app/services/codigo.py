"""Serviço de código de obra: gerar/ver/revogar (arquiteto) e resgatar (entrar como pendente)."""

import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit import log_event
from app.services.common import actor_name, obra_writable

# Alfabeto sem caracteres ambíguos (0/O, 1/I/L).
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _gen_code(n: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


async def gerar_codigo(session: AsyncSession, user_id: str, obra_id: uuid.UUID, papel: str) -> dict:
    cur = await obra_writable(session, obra_id)
    # serializa a regeneração por obra (evita 500 espúrio em chamadas concorrentes)
    await session.execute(
        text("select pg_advisory_xact_lock(hashtextextended(:oid, 0))"),
        {"oid": str(obra_id)},
    )
    # revoga o código ativo anterior (um ativo por obra)
    await session.execute(
        text(
            """update public.obra_codigos set revoked_at = now()
               where obra_id = cast(:oid as uuid) and revoked_at is null"""
        ),
        {"oid": str(obra_id)},
    )
    row = None
    for _ in range(5):  # retry em colisão (rara) do código único global
        code = _gen_code()
        try:
            async with session.begin_nested():  # savepoint p/ não envenenar a transação
                row = (
                    await session.execute(
                        text(
                            """
                            insert into public.obra_codigos
                                (obra_id, codigo, papel, expires_at, created_by)
                            values (cast(:oid as uuid), :code,
                                    cast(:papel as public.papel_obra),
                                    now() + interval '24 hours', (select auth.uid()))
                            returning codigo, papel, expires_at
                            """
                        ),
                        {"oid": str(obra_id), "code": code, "papel": papel},
                    )
                ).first()
            break
        except IntegrityError:
            row = None
            continue
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "não foi possível gerar código")

    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="codigo.gerado",
        entity_type="obra",
        entity_id=obra_id,
        changed={"papel": papel},
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return dict(row._mapping)


async def get_codigo_ativo(session: AsyncSession, obra_id: uuid.UUID) -> dict:
    await obra_writable(session, obra_id)  # só arquiteto vê/compartilha o código
    row = (
        await session.execute(
            text(
                """select codigo, papel, expires_at from public.obra_codigos
                   where obra_id = cast(:oid as uuid)
                     and revoked_at is null and expires_at > now()"""
            ),
            {"oid": str(obra_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "nenhum código ativo")
    return dict(row._mapping)


async def revogar_codigo(session: AsyncSession, user_id: str, obra_id: uuid.UUID) -> dict:
    cur = await obra_writable(session, obra_id)
    res = (
        await session.execute(
            text(
                """update public.obra_codigos set revoked_at = now()
                   where obra_id = cast(:oid as uuid) and revoked_at is null
                   returning id"""
            ),
            {"oid": str(obra_id)},
        )
    ).first()
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "nenhum código ativo")
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="codigo.revogado",
        entity_type="obra",
        entity_id=obra_id,
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return {"revoked": True}


async def resgatar(session: AsyncSession, codigo: str) -> dict:
    """Entra na obra como PENDENTE via a função SECURITY DEFINER (quem entra ainda não é membro).
    Não auditamos aqui (pendente não enxerga a obra pela RLS); o evento auditado é o aceite."""
    try:
        row = (
            await session.execute(
                text("select public.resgatar_codigo_obra(:c) as obra_id"),
                {"c": codigo},
            )
        ).first()
    except DBAPIError as e:
        # a função emite errcode 22023 p/ código inválido/expirado; o resto é erro real (500)
        sqlstate = getattr(getattr(e, "orig", None), "sqlstate", None)
        if sqlstate == "22023":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "código inválido ou expirado") from e
        raise
    return {"obra_id": row.obra_id}
