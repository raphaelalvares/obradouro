"""Rotas do checklist: árvore da obra, CRUD de etapas/itens, toggle de estado e import."""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile, status

from app.api.deps import CurrentUserId, DbSession
from app.core.http import content_disposition
from app.schemas.checklist import (
    AmbienteCreate,
    AmbienteOut,
    AmbientesReorder,
    AmbienteUpdate,
    ChecklistTreeOut,
    CronogramaAplicarIn,
    DatasIn,
    DepCreate,
    DepOut,
    DepUpdate,
    EtapaConclusao,
    EtapaCreate,
    EtapaOut,
    EtapaRename,
    EtapaReorder,
    ImportResumoOut,
    ItemCreate,
    ItemDetalhes,
    ItemDuracaoIn,
    ItemEstado,
    ItemOut,
    ItemRename,
    RecalcularIn,
    SubetapaConclusao,
    SubetapaCreate,
    SubetapaOut,
    SubetapaRename,
    SubetapaReorder,
)
from app.services import ambientes as amb_svc
from app.services import checklist as svc
from app.services import checklist_pdf as pdf_svc
from app.services import dependencias as dep_svc

router = APIRouter()


@router.get("/{obra_id}/checklist", response_model=ChecklistTreeOut)
async def get_tree(obra_id: uuid.UUID, session: DbSession):
    return await svc.get_tree(session, obra_id)


@router.get("/{obra_id}/checklist/pdf")
async def checklist_pdf(obra_id: uuid.UUID, session: DbSession):
    """PDF do checklist p/ impressão (premium 'export_pdf'; 403 + upsell se o plano não inclui)."""
    pdf = await pdf_svc.gerar_pdf(session, obra_id)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition(f"cronograma-{obra_id}.pdf", inline=False)
        },
    )


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


@router.patch("/{obra_id}/etapas/{etapa_id}/datas", response_model=EtapaOut)
async def set_etapa_datas(
    obra_id: uuid.UUID,
    etapa_id: uuid.UUID,
    data: DatasIn,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.set_etapa_datas(session, user_id, obra_id, etapa_id, data)


@router.patch("/{obra_id}/etapas/{etapa_id}/concluida", response_model=EtapaOut)
async def set_etapa_concluida(
    obra_id: uuid.UUID,
    etapa_id: uuid.UUID,
    data: EtapaConclusao,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.set_etapa_concluida(session, user_id, obra_id, etapa_id, data)


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


# ============================ subetapas ============================
@router.post(
    "/{obra_id}/subetapas", response_model=SubetapaOut, status_code=status.HTTP_201_CREATED
)
async def create_subetapa(
    obra_id: uuid.UUID, data: SubetapaCreate, session: DbSession, user_id: CurrentUserId
):
    return await svc.create_subetapa(session, user_id, obra_id, data)


@router.patch("/{obra_id}/subetapas/{subetapa_id}", response_model=SubetapaOut)
async def rename_subetapa(
    obra_id: uuid.UUID,
    subetapa_id: uuid.UUID,
    data: SubetapaRename,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.rename_subetapa(session, user_id, obra_id, subetapa_id, data.nome)


@router.patch("/{obra_id}/subetapas/{subetapa_id}/datas", response_model=SubetapaOut)
async def set_subetapa_datas(
    obra_id: uuid.UUID,
    subetapa_id: uuid.UUID,
    data: DatasIn,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.set_subetapa_datas(session, user_id, obra_id, subetapa_id, data)


@router.patch("/{obra_id}/subetapas/{subetapa_id}/concluida", response_model=SubetapaOut)
async def set_subetapa_concluida(
    obra_id: uuid.UUID,
    subetapa_id: uuid.UUID,
    data: SubetapaConclusao,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.set_subetapa_concluida(session, user_id, obra_id, subetapa_id, data)


@router.patch("/{obra_id}/subetapas/{subetapa_id}/ordem", response_model=SubetapaOut)
async def reorder_subetapa(
    obra_id: uuid.UUID,
    subetapa_id: uuid.UUID,
    data: SubetapaReorder,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.reorder_subetapa(session, user_id, obra_id, subetapa_id, data.ordem)


@router.delete("/{obra_id}/subetapas/{subetapa_id}")
async def delete_subetapa(
    obra_id: uuid.UUID, subetapa_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await svc.delete_subetapa(session, user_id, obra_id, subetapa_id)


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


@router.patch("/{obra_id}/itens/{item_id}/datas", response_model=ItemOut)
async def set_item_datas(
    obra_id: uuid.UUID,
    item_id: uuid.UUID,
    data: DatasIn,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await svc.set_item_datas(session, user_id, obra_id, item_id, data)


@router.patch("/{obra_id}/itens/{item_id}/duracao", response_model=ItemOut)
async def set_item_duracao(
    obra_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ItemDuracaoIn,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await dep_svc.set_item_duracao(session, user_id, obra_id, item_id, data)


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


@router.post("/{obra_id}/cronograma", response_model=ChecklistTreeOut)
async def aplicar_cronograma(
    obra_id: uuid.UUID,
    data: CronogramaAplicarIn,
    session: DbSession,
    user_id: CurrentUserId,
):
    """Aplica o cronograma macro (prévia editada): datas de itens/etapas + janela da obra."""
    return await svc.aplicar_cronograma(session, user_id, obra_id, data)


# ============================ ambientes (cômodos) ============================
@router.post(
    "/{obra_id}/ambientes", response_model=AmbienteOut, status_code=status.HTTP_201_CREATED
)
async def criar_ambiente(
    obra_id: uuid.UUID, data: AmbienteCreate, session: DbSession, user_id: CurrentUserId
):
    return await amb_svc.criar(session, user_id, obra_id, data)


@router.patch("/{obra_id}/ambientes/reordenar", response_model=list[AmbienteOut])
async def reordenar_ambientes(
    obra_id: uuid.UUID, data: AmbientesReorder, session: DbSession, user_id: CurrentUserId
):
    return await amb_svc.reordenar(session, user_id, obra_id, data.ids)


@router.patch("/{obra_id}/ambientes/{amb_id}", response_model=AmbienteOut)
async def atualizar_ambiente(
    obra_id: uuid.UUID,
    amb_id: uuid.UUID,
    data: AmbienteUpdate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await amb_svc.atualizar(session, user_id, obra_id, amb_id, data)


@router.delete("/{obra_id}/ambientes/{amb_id}")
async def excluir_ambiente(
    obra_id: uuid.UUID, amb_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await amb_svc.excluir(session, user_id, obra_id, amb_id)


# ============================ dependências / cronograma automático ============================
@router.post(
    "/{obra_id}/dependencias", response_model=DepOut, status_code=status.HTTP_201_CREATED
)
async def add_dependencia(
    obra_id: uuid.UUID, data: DepCreate, session: DbSession, user_id: CurrentUserId
):
    return await dep_svc.add_dep(session, user_id, obra_id, data)


@router.patch("/{obra_id}/dependencias/{dep_id}", response_model=DepOut)
async def update_dependencia(
    obra_id: uuid.UUID,
    dep_id: uuid.UUID,
    data: DepUpdate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await dep_svc.update_dep(session, user_id, obra_id, dep_id, data)


@router.delete("/{obra_id}/dependencias/{dep_id}")
async def delete_dependencia(
    obra_id: uuid.UUID, dep_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await dep_svc.delete_dep(session, user_id, obra_id, dep_id)


@router.post("/{obra_id}/cronograma/recalcular", response_model=ChecklistTreeOut)
async def recalcular_cronograma(
    obra_id: uuid.UUID, data: RecalcularIn, session: DbSession, user_id: CurrentUserId
):
    """Recalcula as datas pela rede de dependências (forward pass FS, dias corridos)."""
    return await dep_svc.recalcular(session, user_id, obra_id, data.data_inicio)


@router.post("/{obra_id}/checklist/importar", response_model=ImportResumoOut)
async def importar(
    obra_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    arquivo: Annotated[UploadFile, File()],
):
    return await svc.importar(session, user_id, obra_id, arquivo)
