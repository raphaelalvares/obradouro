"""Pipeline do projeto (linha do tempo). Router sem prefixo (caminhos /projetos/{id}/pipeline) —
registrado direto, como portal/projeto_vinculo. GET p/ membros; PATCH p/ arquiteto; iniciar-obra p/
o cliente."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import CurrentUserId, DbSession
from app.core.http import content_disposition
from app.schemas.pipeline import (
    EtapaAnexoOut,
    EtapaLinkCreate,
    EtapaUpdate,
    IniciarObraDecisao,
    PipelineOut,
)
from app.services import pipeline as pipeline_svc

router = APIRouter()


@router.get("/projetos/{projeto_id}/pipeline", response_model=PipelineOut, tags=["pipeline"])
async def listar(projeto_id: uuid.UUID, session: DbSession):
    return await pipeline_svc.listar(session, projeto_id)


@router.patch(
    "/projetos/{projeto_id}/pipeline/{etapa}", response_model=PipelineOut, tags=["pipeline"]
)
async def atualizar(
    projeto_id: uuid.UUID,
    etapa: str,
    data: EtapaUpdate,
    session: DbSession,
    user_id: CurrentUserId,
):
    enviado = data.model_fields_set
    return await pipeline_svc.atualizar_etapa(
        session,
        user_id,
        projeto_id,
        etapa,
        novo_status=data.status,
        data_prevista=data.data_prevista,
        set_data="data_prevista" in enviado,
        observacao=data.observacao,
        set_obs="observacao" in enviado,
    )


@router.post(
    "/projetos/{projeto_id}/pipeline/iniciar-obra", response_model=PipelineOut, tags=["pipeline"]
)
async def iniciar_obra(
    projeto_id: uuid.UUID, data: IniciarObraDecisao, session: DbSession, user_id: CurrentUserId
):
    return await pipeline_svc.decidir_iniciar_obra(session, projeto_id, data.decisao)


# ============================ material da etapa (arquivo | link) ============================
@router.post(
    "/projetos/{projeto_id}/pipeline/{etapa}/anexos",
    response_model=EtapaAnexoOut,
    status_code=status.HTTP_201_CREATED,
    tags=["pipeline"],
)
async def subir_etapa_arquivo(
    projeto_id: uuid.UUID,
    etapa: str,
    session: DbSession,
    user_id: CurrentUserId,
    id: Annotated[uuid.UUID, Form()],
    arquivo: Annotated[UploadFile, File()],
    label: Annotated[str | None, Form(max_length=200)] = None,
):
    return await pipeline_svc.upload_etapa_arquivo(
        session, user_id, projeto_id, etapa, id, arquivo, label
    )


@router.post(
    "/projetos/{projeto_id}/pipeline/{etapa}/anexos/link",
    response_model=EtapaAnexoOut,
    status_code=status.HTTP_201_CREATED,
    tags=["pipeline"],
)
async def adicionar_etapa_link(
    projeto_id: uuid.UUID,
    etapa: str,
    data: EtapaLinkCreate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await pipeline_svc.adicionar_link(session, user_id, projeto_id, etapa, data)


@router.get("/projetos/{projeto_id}/pipeline/anexos/{anexo_id}/conteudo", tags=["pipeline"])
async def conteudo_etapa_anexo(
    projeto_id: uuid.UUID,
    anexo_id: uuid.UUID,
    session: DbSession,
    _user_id: CurrentUserId,
    tipo: Annotated[str, Query(pattern="^(full|thumb)$")] = "full",
):
    data, content_type, nome = await pipeline_svc.serve_etapa_anexo(
        session, projeto_id, anexo_id, tipo
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": content_disposition(nome, inline=True),
        },
    )


@router.delete("/projetos/{projeto_id}/pipeline/anexos/{anexo_id}", tags=["pipeline"])
async def remover_etapa_anexo(
    projeto_id: uuid.UUID, anexo_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await pipeline_svc.excluir_etapa_anexo(session, user_id, projeto_id, anexo_id)
