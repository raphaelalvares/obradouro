"""Rotas escopadas à obra: membros, convite por email e código de obra. Prefixo /obras."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUserId, DbSession
from app.schemas.codigo import CodigoCreate, CodigoOut
from app.schemas.convites import ConviteCreate, ConviteEnviadoOut
from app.schemas.membros import MembroOut
from app.services import codigo as codigo_svc
from app.services import convites as convites_svc
from app.services import membros as membros_svc

router = APIRouter()


@router.get("/{obra_id}/membros", response_model=list[MembroOut])
async def list_membros(obra_id: uuid.UUID, session: DbSession):
    return await membros_svc.list_membros(session, obra_id)


@router.delete("/{obra_id}/membros/{membro_id}")
async def remove_membro(
    obra_id: uuid.UUID, membro_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await membros_svc.remove_membro(session, user_id, obra_id, membro_id)


@router.post(
    "/{obra_id}/convites",
    response_model=ConviteEnviadoOut,
    status_code=status.HTTP_201_CREATED,
)
async def convidar(
    obra_id: uuid.UUID, data: ConviteCreate, session: DbSession, user_id: CurrentUserId
):
    return await convites_svc.convidar_por_email(session, user_id, obra_id, data.email, data.papel)


@router.post("/{obra_id}/codigo", response_model=CodigoOut, status_code=status.HTTP_201_CREATED)
async def gerar_codigo(
    obra_id: uuid.UUID, data: CodigoCreate, session: DbSession, user_id: CurrentUserId
):
    return await codigo_svc.gerar_codigo(session, user_id, obra_id, data.papel)


@router.get("/{obra_id}/codigo", response_model=CodigoOut)
async def get_codigo(obra_id: uuid.UUID, session: DbSession):
    return await codigo_svc.get_codigo_ativo(session, obra_id)


@router.delete("/{obra_id}/codigo")
async def revogar_codigo(obra_id: uuid.UUID, session: DbSession, user_id: CurrentUserId):
    return await codigo_svc.revogar_codigo(session, user_id, obra_id)
