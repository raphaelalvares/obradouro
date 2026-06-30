"""Pipeline do projeto (linha do tempo). Router sem prefixo (caminhos /projetos/{id}/pipeline) —
registrado direto, como portal/projeto_vinculo. GET p/ membros; PATCH p/ arquiteto; iniciar-obra p/
o cliente."""

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUserId, DbSession
from app.schemas.pipeline import EtapaUpdate, IniciarObraDecisao, PipelineOut
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
