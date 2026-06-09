"""Rotas do micro-CRM (Comercial): funil de oportunidades. Tenant-scoped (só o arquiteto/dono)."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUserId, DbSession
from app.schemas.obras import ObraOut
from app.schemas.oportunidades import (
    OportunidadeConverter,
    OportunidadeCreate,
    OportunidadeOut,
    OportunidadeUpdate,
)
from app.services import oportunidades as svc

router = APIRouter()


@router.get("", response_model=list[OportunidadeOut])
async def list_oportunidades(session: DbSession):
    return await svc.list_oportunidades(session)


@router.post("", response_model=OportunidadeOut, status_code=status.HTTP_201_CREATED)
async def create_oportunidade(
    data: OportunidadeCreate, session: DbSession, user_id: CurrentUserId
):
    return await svc.create_oportunidade(session, user_id, data)


@router.get("/{op_id}", response_model=OportunidadeOut)
async def get_oportunidade(op_id: uuid.UUID, session: DbSession):
    return await svc.get_oportunidade(session, op_id)


@router.patch("/{op_id}", response_model=OportunidadeOut)
async def update_oportunidade(
    op_id: uuid.UUID, data: OportunidadeUpdate, session: DbSession, user_id: CurrentUserId
):
    return await svc.update_oportunidade(session, user_id, op_id, data)


@router.post("/{op_id}/converter", response_model=ObraOut)
async def converter_oportunidade(
    op_id: uuid.UUID, data: OportunidadeConverter, session: DbSession, user_id: CurrentUserId
):
    """Cria uma obra a partir da oportunidade (ganho) e vincula. Pode dar soft-limit 403 (plano)."""
    return await svc.converter(session, user_id, op_id, data)


@router.delete("/{op_id}")
async def delete_oportunidade(op_id: uuid.UUID, session: DbSession, user_id: CurrentUserId):
    return await svc.delete_oportunidade(session, user_id, op_id)
