"""Rotas do checklist: árvore da obra, CRUD de etapas/itens, toggle de estado e import."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from app.api.deps import CurrentUserId, DbSession
from app.schemas.checklist import (
    ChecklistTreeOut,
    EtapaCreate,
    EtapaOut,
    EtapaRename,
    EtapaReorder,
    ImportResumoOut,
    ItemCreate,
    ItemDetalhes,
    ItemEstado,
    ItemOut,
    ItemRename,
)
from app.services import checklist as svc

router = APIRouter()


@router.get("/{obra_id}/checklist", response_model=ChecklistTreeOut)
async def get_tree(obra_id: uuid.UUID, session: DbSession):
    return await svc.get_tree(session, obra_id)


@router.post("/{obra_id}/etapas", response_model=EtapaOut, status_code=status.HTTP_201_CREATED)
async def create_etapa(
    obra_id: uuid.UUID, data: EtapaCreate, session: DbSession, user_id: CurrentUserId
):
    return await svc.create_etapa(session, user_id, obra_id, data)


@router.patch("/{obra_id}/etapas/{etapa_id}", response_model=EtapaOut)
async def rename_etapa(
    obra_id: uuid.UUID,
    etapa_id: uuid.UUID,
    data: EtapaRename,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.rename_etapa(session, user_id, obra_id, etapa_id, data.nome)


@router.patch("/{obra_id}/etapas/{etapa_id}/ordem", response_model=EtapaOut)
async def reorder_etapa(
    obra_id: uuid.UUID,
    etapa_id: uuid.UUID,
    data: EtapaReorder,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.reorder_etapa(session, user_id, obra_id, etapa_id, data.ordem)


@router.delete("/{obra_id}/etapas/{etapa_id}")
async def delete_etapa(
    obra_id: uuid.UUID, etapa_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await svc.delete_etapa(session, user_id, obra_id, etapa_id)


@router.post("/{obra_id}/itens", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    obra_id: uuid.UUID, data: ItemCreate, session: DbSession, user_id: CurrentUserId
):
    return await svc.create_item(session, user_id, obra_id, data)


@router.patch("/{obra_id}/itens/{item_id}", response_model=ItemOut)
async def rename_item(
    obra_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ItemRename,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.rename_item(session, user_id, obra_id, item_id, data.nome)


@router.patch("/{obra_id}/itens/{item_id}/detalhes", response_model=ItemOut)
async def atualizar_detalhes(
    obra_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ItemDetalhes,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.atualizar_detalhes(session, user_id, obra_id, item_id, data)


@router.patch("/{obra_id}/itens/{item_id}/estado", response_model=ItemOut)
async def toggle_item(
    obra_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ItemEstado,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.set_item_estado(session, user_id, obra_id, item_id, data)


@router.delete("/{obra_id}/itens/{item_id}")
async def delete_item(
    obra_id: uuid.UUID, item_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await svc.delete_item(session, user_id, obra_id, item_id)


@router.post("/{obra_id}/checklist/importar", response_model=ImportResumoOut)
async def importar(
    obra_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    arquivo: Annotated[UploadFile, File()],
):
    return await svc.importar(session, user_id, obra_id, arquivo)
