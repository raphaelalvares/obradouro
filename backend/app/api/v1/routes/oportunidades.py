"""Rotas do micro-CRM (Comercial): funil de oportunidades. Tenant-scoped (só o arquiteto/dono)."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUserId, DbSession
from app.schemas.obras import ObraOut
from app.schemas.oportunidades import (
    ComentarioCreate,
    ComentarioOut,
    ComentarioUpdate,
    OportunidadeConverter,
    OportunidadeCreate,
    OportunidadeCriarProjeto,
    OportunidadeOut,
    OportunidadeUpdate,
    OportunidadeVincularProjeto,
)
from app.schemas.projetos import ProjetoOut
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


# ============================ elo com projeto ============================
@router.post("/{op_id}/criar-projeto", response_model=ProjetoOut)
async def criar_projeto_da_oportunidade(
    op_id: uuid.UUID, data: OportunidadeCriarProjeto, session: DbSession, user_id: CurrentUserId
):
    """Cria um projeto a partir da oportunidade e vincula (costura lead → projeto)."""
    return await svc.criar_projeto_da_oportunidade(session, user_id, op_id, data)


@router.post("/{op_id}/vincular-projeto", response_model=OportunidadeOut)
async def vincular_projeto(
    op_id: uuid.UUID, data: OportunidadeVincularProjeto, session: DbSession, user_id: CurrentUserId
):
    return await svc.vincular_projeto(session, user_id, op_id, data)


# ============================ comentários ============================
@router.get("/{op_id}/comentarios", response_model=list[ComentarioOut])
async def list_comentarios(op_id: uuid.UUID, session: DbSession):
    return await svc.list_comentarios(session, op_id)


@router.post(
    "/{op_id}/comentarios", response_model=ComentarioOut, status_code=status.HTTP_201_CREATED
)
async def add_comentario(
    op_id: uuid.UUID, data: ComentarioCreate, session: DbSession, user_id: CurrentUserId
):
    return await svc.add_comentario(session, user_id, op_id, data)


@router.patch("/{op_id}/comentarios/{c_id}", response_model=ComentarioOut)
async def edit_comentario(
    op_id: uuid.UUID,
    c_id: uuid.UUID,
    data: ComentarioUpdate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.edit_comentario(session, user_id, op_id, c_id, data)


@router.delete("/{op_id}/comentarios/{c_id}")
async def delete_comentario(
    op_id: uuid.UUID, c_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await svc.delete_comentario(session, user_id, op_id, c_id)
