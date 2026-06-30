"""Pipeline do projeto (linha do tempo). Router sem prefixo (caminhos /projetos/{id}/pipeline) —
registrado direto, como portal/projeto_vinculo. GET p/ membros; PATCH p/ arquiteto; iniciar-obra p/
o cliente."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import CurrentUserId, DbSession
from app.core.http import content_disposition
from app.schemas.pipeline import (
    Ambiente3DOut,
    AmbienteProjetoCreate,
    AmbienteProjetoUpdate,
    AmbientesProjetoReorder,
    Aprovacao3DDecisao,
    EtapaAnexoOut,
    EtapaLinkCreate,
    EtapaUpdate,
    IniciarObraDecisao,
    ManualItemCreate,
    ManualItemOut,
    ManualItemUpdate,
    ManualItensReorder,
    PipelineOut,
)
from app.services import ambientes_projeto as amb3d_svc
from app.services import manual_projeto as manual_svc
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


# ==================== 3D / aprovação por AMBIENTE (etapa projeto_3d) ====================
# Rotas estáticas (.../ambientes-3d, .../reordenar) ANTES das paramétricas; profundidade
# distinta das genéricas /pipeline/{etapa} e /pipeline/anexos/... → sem colisão.
@router.post(
    "/projetos/{projeto_id}/pipeline/ambientes-3d",
    response_model=Ambiente3DOut,
    status_code=status.HTTP_201_CREATED,
    tags=["pipeline"],
)
async def criar_ambiente_3d(
    projeto_id: uuid.UUID, data: AmbienteProjetoCreate, session: DbSession, user_id: CurrentUserId
):
    return await amb3d_svc.criar(session, user_id, projeto_id, data)


@router.patch(
    "/projetos/{projeto_id}/pipeline/ambientes-3d/reordenar",
    response_model=list[Ambiente3DOut],
    tags=["pipeline"],
)
async def reordenar_ambientes_3d(
    projeto_id: uuid.UUID, data: AmbientesProjetoReorder, session: DbSession, user_id: CurrentUserId
):
    return await amb3d_svc.reordenar(session, user_id, projeto_id, data.ids)


@router.patch(
    "/projetos/{projeto_id}/pipeline/ambientes-3d/{amb_id}",
    response_model=Ambiente3DOut,
    tags=["pipeline"],
)
async def atualizar_ambiente_3d(
    projeto_id: uuid.UUID,
    amb_id: uuid.UUID,
    data: AmbienteProjetoUpdate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await amb3d_svc.atualizar(session, user_id, projeto_id, amb_id, data)


@router.delete("/projetos/{projeto_id}/pipeline/ambientes-3d/{amb_id}", tags=["pipeline"])
async def excluir_ambiente_3d(
    projeto_id: uuid.UUID, amb_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await amb3d_svc.excluir(session, user_id, projeto_id, amb_id)


@router.post(
    "/projetos/{projeto_id}/pipeline/ambientes-3d/{amb_id}/enviar",
    response_model=Ambiente3DOut,
    tags=["pipeline"],
)
async def enviar_ambiente_3d(
    projeto_id: uuid.UUID, amb_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await amb3d_svc.enviar_3d(session, user_id, projeto_id, amb_id)


@router.post(
    "/projetos/{projeto_id}/pipeline/ambientes-3d/{amb_id}/decisao",
    response_model=Ambiente3DOut,
    tags=["pipeline"],
)
async def decidir_ambiente_3d(
    projeto_id: uuid.UUID,
    amb_id: uuid.UUID,
    data: Aprovacao3DDecisao,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await amb3d_svc.decidir_3d(session, user_id, projeto_id, amb_id, data)


@router.post(
    "/projetos/{projeto_id}/pipeline/ambientes-3d/{amb_id}/anexos",
    response_model=EtapaAnexoOut,
    status_code=status.HTTP_201_CREATED,
    tags=["pipeline"],
)
async def subir_anexo_ambiente_3d(
    projeto_id: uuid.UUID,
    amb_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    id: Annotated[uuid.UUID, Form()],
    arquivo: Annotated[UploadFile, File()],
    label: Annotated[str | None, Form(max_length=200)] = None,
):
    return await pipeline_svc.upload_etapa_arquivo(
        session, user_id, projeto_id, "projeto_3d", id, arquivo, label, ambiente_id=amb_id
    )


@router.post(
    "/projetos/{projeto_id}/pipeline/ambientes-3d/{amb_id}/anexos/link",
    response_model=EtapaAnexoOut,
    status_code=status.HTTP_201_CREATED,
    tags=["pipeline"],
)
async def adicionar_link_ambiente_3d(
    projeto_id: uuid.UUID,
    amb_id: uuid.UUID,
    data: EtapaLinkCreate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await pipeline_svc.adicionar_link(
        session, user_id, projeto_id, "projeto_3d", data, ambiente_id=amb_id
    )


# ==================== Manual do proprietário (etapa manual) ====================
# Rotas estáticas (.../manual, .../reordenar) ANTES das paramétricas; profundidade distinta das
# genéricas /pipeline/{etapa} e /pipeline/{etapa}/anexos → sem colisão (manual é etapa válida).
@router.post(
    "/projetos/{projeto_id}/pipeline/manual",
    response_model=ManualItemOut,
    status_code=status.HTTP_201_CREATED,
    tags=["pipeline"],
)
async def criar_manual_item(
    projeto_id: uuid.UUID, data: ManualItemCreate, session: DbSession, user_id: CurrentUserId
):
    return await manual_svc.criar(session, user_id, projeto_id, data)


@router.patch(
    "/projetos/{projeto_id}/pipeline/manual/reordenar",
    response_model=list[ManualItemOut],
    tags=["pipeline"],
)
async def reordenar_manual_itens(
    projeto_id: uuid.UUID, data: ManualItensReorder, session: DbSession, user_id: CurrentUserId
):
    return await manual_svc.reordenar(session, user_id, projeto_id, data.ids)


@router.patch(
    "/projetos/{projeto_id}/pipeline/manual/{item_id}",
    response_model=ManualItemOut,
    tags=["pipeline"],
)
async def atualizar_manual_item(
    projeto_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ManualItemUpdate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await manual_svc.atualizar(session, user_id, projeto_id, item_id, data)


@router.delete("/projetos/{projeto_id}/pipeline/manual/{item_id}", tags=["pipeline"])
async def excluir_manual_item(
    projeto_id: uuid.UUID, item_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await manual_svc.excluir(session, user_id, projeto_id, item_id)


@router.post(
    "/projetos/{projeto_id}/pipeline/manual/{item_id}/anexos",
    response_model=EtapaAnexoOut,
    status_code=status.HTTP_201_CREATED,
    tags=["pipeline"],
)
async def subir_anexo_manual_item(
    projeto_id: uuid.UUID,
    item_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    id: Annotated[uuid.UUID, Form()],
    arquivo: Annotated[UploadFile, File()],
    label: Annotated[str | None, Form(max_length=200)] = None,
):
    return await pipeline_svc.upload_etapa_arquivo(
        session, user_id, projeto_id, "manual", id, arquivo, label, manual_item_id=item_id
    )


@router.post(
    "/projetos/{projeto_id}/pipeline/manual/{item_id}/anexos/link",
    response_model=EtapaAnexoOut,
    status_code=status.HTTP_201_CREATED,
    tags=["pipeline"],
)
async def adicionar_link_manual_item(
    projeto_id: uuid.UUID,
    item_id: uuid.UUID,
    data: EtapaLinkCreate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await pipeline_svc.adicionar_link(
        session, user_id, projeto_id, "manual", data, manual_item_id=item_id
    )


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
