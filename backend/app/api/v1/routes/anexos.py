"""Rotas de anexos: upload (multipart), galeria por alvo, stream de bytes, delete e reconciliação.

No modelo API-only o byte é servido PELA API (não por URL pública do storage): /conteudo exige JWT
(via DbSession), então o front busca a imagem por fetch autenticado e usa um blob URL — não dá p/
apontar <img src> direto para cá sem o header Authorization.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import CurrentUserId, DbSession
from app.core.http import content_disposition
from app.schemas.anexos import AnexoCreate, AnexoOut, LegendaUpdate, ParentType
from app.services import anexos as svc

router = APIRouter()


@router.post("/{obra_id}/anexos", response_model=AnexoOut, status_code=status.HTTP_201_CREATED)
async def criar_anexo(
    obra_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    id: Annotated[uuid.UUID, Form()],  # gerado no cliente (offline/dual-ID)
    parent_type: Annotated[ParentType, Form()],
    parent_id: Annotated[uuid.UUID, Form()],
    arquivo: Annotated[UploadFile, File()],
    legenda: Annotated[str | None, Form()] = None,
):
    data = AnexoCreate(id=id, parent_type=parent_type, parent_id=parent_id, legenda=legenda)
    return await svc.upload(session, user_id, obra_id, data, arquivo)


@router.get("/{obra_id}/anexos", response_model=list[AnexoOut])
async def listar_anexos(
    obra_id: uuid.UUID,
    session: DbSession,
    parent_type: Annotated[ParentType, Query()],
    parent_id: Annotated[uuid.UUID, Query()],
):
    return await svc.list_anexos(session, obra_id, parent_type, parent_id)


# rota estática antes da paramétrica {anexo_id} (defensivo; uuid não casa "reconciliar")
@router.post("/{obra_id}/anexos/reconciliar")
async def reconciliar_anexos(obra_id: uuid.UUID, session: DbSession, user_id: CurrentUserId):
    return await svc.reconciliar(session, user_id, obra_id)


@router.get("/{obra_id}/anexos/{anexo_id}/conteudo")
async def conteudo_anexo(
    obra_id: uuid.UUID,
    anexo_id: uuid.UUID,
    session: DbSession,
    _user_id: CurrentUserId,
    tipo: Annotated[str, Query(pattern="^(full|thumb)$")] = "thumb",
):
    data, content_type, nome = await svc.serve_bytes(session, obra_id, anexo_id, tipo)
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": content_disposition(nome, inline=True),
        },
    )


@router.patch("/{obra_id}/anexos/{anexo_id}", response_model=AnexoOut)
async def editar_legenda(
    obra_id: uuid.UUID,
    anexo_id: uuid.UUID,
    data: LegendaUpdate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.patch_legenda(session, user_id, obra_id, anexo_id, data.legenda)


@router.delete("/{obra_id}/anexos/{anexo_id}")
async def deletar_anexo(
    obra_id: uuid.UUID, anexo_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await svc.delete_anexo(session, user_id, obra_id, anexo_id)
