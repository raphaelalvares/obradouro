"""Rotas do estoque (NF-e): import do XML, notas, conferência, nome fiel, data de chegada, saldo.
Prefixo /obras (escopo da obra), igual a checklist/anexos."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from app.api.deps import CurrentUserId, DbSession
from app.schemas.estoque import (
    ConferenciaIn,
    ImportResumoNotaOut,
    ItemNomeUpdate,
    NotaDetalheOut,
    NotaItemOut,
    NotaResumoOut,
    NotaUpdate,
    SaldoItemOut,
)
from app.services import estoque as svc

router = APIRouter()


@router.post("/{obra_id}/estoque/importar", response_model=ImportResumoNotaOut)
async def importar(
    obra_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    arquivo: Annotated[UploadFile, File()],
):
    return await svc.importar(session, user_id, obra_id, arquivo)


@router.get("/{obra_id}/estoque/notas", response_model=list[NotaResumoOut])
async def listar_notas(obra_id: uuid.UUID, session: DbSession):
    return await svc.list_notas(session, obra_id)


@router.get("/{obra_id}/estoque/notas/{nota_id}", response_model=NotaDetalheOut)
async def get_nota(obra_id: uuid.UUID, nota_id: uuid.UUID, session: DbSession):
    return await svc.get_nota(session, obra_id, nota_id)


@router.patch("/{obra_id}/estoque/notas/{nota_id}", response_model=NotaDetalheOut)
async def atualizar_nota(
    obra_id: uuid.UUID,
    nota_id: uuid.UUID,
    data: NotaUpdate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.atualizar_nota(session, user_id, obra_id, nota_id, data)


@router.delete("/{obra_id}/estoque/notas/{nota_id}")
async def excluir_nota(
    obra_id: uuid.UUID, nota_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await svc.excluir_nota(session, user_id, obra_id, nota_id)


@router.patch("/{obra_id}/estoque/itens/{item_id}/nome", response_model=NotaItemOut)
async def editar_nome_item(
    obra_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ItemNomeUpdate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.editar_nome_item(session, user_id, obra_id, item_id, data)


@router.patch("/{obra_id}/estoque/itens/{item_id}/conferencia", response_model=NotaItemOut)
async def conferir_item(
    obra_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ConferenciaIn,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.conferir_item(session, user_id, obra_id, item_id, data)


@router.get("/{obra_id}/estoque/saldo", response_model=list[SaldoItemOut])
async def saldo(obra_id: uuid.UUID, session: DbSession):
    return await svc.saldo(session, obra_id)
