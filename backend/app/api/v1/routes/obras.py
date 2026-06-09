"""Rotas de obras (CRUD + arquivar/reativar) e leitura do audit log da obra."""

import uuid

from fastapi import APIRouter, status

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


@router.get("/{obra_id}/audit", response_model=list[AuditEntryOut])
async def obra_audit(obra_id: uuid.UUID, session: DbSession):
    return await obras_svc.list_audit(session, obra_id)
