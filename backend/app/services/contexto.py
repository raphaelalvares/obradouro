"""Cartão de CONTEXTO do cliente (1:1 com a oportunidade): perfil estruturado + resumo curto.

Degrada limpo se a migration 0087 ainda não foi aplicada (tabela ausente → leitura devolve vazio,
escrita devolve 503 explícito). Tenant-scoped via RLS (espelha oportunidade_comentarios). Valida o
dono via get_oportunidade (404 limpo) antes de tocar no contexto.
"""

import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.contexto import ContextoUpsert
from app.services import oportunidades as op_svc
from app.services.audit import log_event
from app.services.common import actor_name


def _tabela_ausente(e: DBAPIError) -> bool:
    """42P01 = relation does not exist → migration 0087 ainda não aplicada."""
    return getattr(getattr(e, "orig", None), "sqlstate", None) == "42P01"


def _map_42501(e: DBAPIError) -> HTTPException | None:
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


def _vazio(op_id: uuid.UUID) -> dict:
    return {
        "oportunidade_id": op_id,
        "perfil": {},
        "resumo": None,
        "existe": False,
        "atualizado_em": None,
    }


async def get_contexto(session: AsyncSession, op_id: uuid.UUID) -> dict:
    await op_svc.get_oportunidade(session, op_id)  # 404 se não for do dono
    try:
        # savepoint: se a tabela não existe (42P01, migration 0087 não aplicada) o erro reverte só o
        # savepoint — sem ele, a txn aborta e o COMMIT do teardown daria 500 em vez de degradar.
        async with session.begin_nested():
            row = (
                await session.execute(
                    text(
                        "select oportunidade_id, perfil, resumo, updated_at "
                        "from public.oportunidade_contexto "
                        "where oportunidade_id = cast(:id as uuid)"
                    ),
                    {"id": str(op_id)},
                )
            ).first()
    except DBAPIError as e:
        if _tabela_ausente(e):
            return _vazio(op_id)
        raise
    if row is None:
        return _vazio(op_id)
    m = dict(row._mapping)
    perfil = m["perfil"]
    if isinstance(perfil, str):  # asyncpg pode devolver jsonb como texto
        perfil = json.loads(perfil)
    return {
        "oportunidade_id": m["oportunidade_id"],
        "perfil": perfil or {},
        "resumo": m["resumo"],
        "existe": True,
        "atualizado_em": m["updated_at"],
    }


async def upsert_contexto(
    session: AsyncSession, user_id: str, op_id: uuid.UUID, data: ContextoUpsert
) -> dict:
    op = await op_svc.get_oportunidade(session, op_id)  # 404 se não for do dono
    perfil_json = json.dumps(data.perfil.model_dump(exclude_none=True))
    try:
        # savepoint (como em create_oportunidade): contém 42P01 (migration ausente) / 42501 (guard)
        # sem abortar a txn do request.
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    insert into public.oportunidade_contexto
                      (oportunidade_id, tenant_id, perfil, resumo, updated_by)
                    values
                      (cast(:id as uuid), cast(:t as uuid), cast(:perfil as jsonb), :resumo,
                       cast(:t as uuid))
                    on conflict (oportunidade_id) do update
                      set perfil = excluded.perfil, resumo = excluded.resumo,
                          updated_by = excluded.updated_by
                    """
                ),
                {"id": str(op_id), "t": user_id, "perfil": perfil_json, "resumo": data.resumo},
            )
    except DBAPIError as e:
        if _tabela_ausente(e):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "contexto indisponível — aplique a migration 0087",
            ) from e
        raise (_map_42501(e) or e) from e

    await log_event(
        session,
        tenant=user_id,
        actor_id=user_id,
        obra_id=None,
        action="oportunidade.contexto_atualizado",
        entity_type="oportunidade",
        entity_id=op_id,
        entity_label=op["nome"],
        entity_seq=op["seq_humano"],
        actor_label=await actor_name(session),
    )
    return await get_contexto(session, op_id)
