"""Rotas de obras (CRUD + arquivar/reativar) e leitura do audit log da obra."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUserId, DbSession
from app.schemas.audit import AuditEntryOut
from app.schemas.obras import ObraCreate, ObraDatas, ObraOut, ObraRename
from app.services import obras as obras_svc

router = APIRouter()


@router.post("", response_model=ObraOut, status_code=status.HTTP_201_CREATED)
async def create_obra(data: ObraCreate, session: DbSession, user_id: CurrentUserId):
    return await obras_svc.create_obra(session, user_id, data)


@router.get("", response_model=list[ObraOut])
async def list_obras(session: DbSession):
    return await obras_svc.list_obras(session)


@router.get("/{obra_id}", response_model=ObraOut)
async def get_obra(obra_id: uuid.UUID, session: DbSession):
    return await obras_svc.get_obra(session, obra_id)


@router.patch("/{obra_id}", response_model=ObraOut)
async def rename_obra(
    obra_id: uuid.UUID, data: ObraRename, session: DbSession, user_id: CurrentUserId
):
    return await obras_svc.rename_obra(session, user_id, obra_id, data.nome)


@router.patch("/{obra_id}/datas", response_model=ObraOut)
async def set_obra_datas(
    obra_id: uuid.UUID, data: ObraDatas, session: DbSession, user_id: CurrentUserId
):
    return await obras_svc.set_datas(session, user_id, obra_id, data.data_inicio, data.data_fim)


@router.post("/{obra_id}/arquivar", response_model=ObraOut)
async def arquivar_obra(obra_id: uuid.UUID, session: DbSession, user_id: CurrentUserId):
    return await obras_svc.set_status(session, user_id, obra_id, "arquivada")


@router.post("/{obra_id}/reativar", response_model=ObraOut)
async def reativar_obra(obra_id: uuid.UUID, session: DbSession, user_id: CurrentUserId):
    return await obras_svc.set_status(session, user_id, obra_id, "ativa")


@router.post("/{obra_id}/entrega", response_model=ObraOut)
async def marcar_entrega(obra_id: uuid.UUID, session: DbSession, user_id: CurrentUserId):
    return await obras_svc.marcar_entrega(session, user_id, obra_id, True)


@router.delete("/{obra_id}/entrega", response_model=ObraOut)
async def desmarcar_entrega(obra_id: uuid.UUID, session: DbSession, user_id: CurrentUserId):
    return await obras_svc.marcar_entrega(session, user_id, obra_id, False)


@router.get("/{obra_id}/audit", response_model=list[AuditEntryOut])
async def obra_audit(
    obra_id: uuid.UUID,
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,  # I6: página (mais recentes primeiro)
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await obras_svc.list_audit(session, obra_id, limit=limit, offset=offset)
