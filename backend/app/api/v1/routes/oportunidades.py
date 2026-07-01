"""Rotas do micro-CRM (Comercial): funil de oportunidades. Tenant-scoped (só o arquiteto/dono)."""

import uuid

from fastapi import APIRouter, BackgroundTasks, status

from app.api.deps import CurrentUserId, DbSession
from app.schemas.contexto import ContextoOut, ContextoUpsert
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
from app.schemas.portal import LiberarPortalOut
from app.schemas.projetos import ProjetoOut
from app.services import contexto as contexto_svc
from app.services import notificacoes as notif_svc
from app.services import oportunidades as svc
from app.services import portal as portal_svc

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


# ============================ elo com portal (costura lead → portal) ============================
@router.post("/{op_id}/liberar-portal", response_model=LiberarPortalOut)
async def liberar_portal(
    op_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    background: BackgroundTasks,
):
    """Libera o acesso do cliente no portal usando o e-mail de contato do lead (sem redigitar) e
    envia o link de cadastro (BackgroundTask, best-effort) quando a autorização é nova. Amarra o
    acesso à oportunidade (mesmo cliente do funil ao portal)."""
    out, notif = await portal_svc.autorizar_acesso_da_oportunidade(session, user_id, op_id)
    if notif:
        background.add_task(notif_svc.notificar_convite_cliente, **notif)
    return {
        "email": out["email"],
        "cadastrado": out["cadastrado"],
        "convite_enviado": notif is not None,
    }


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


# ===================== contexto (cartão do cliente — memória do agente) =====================
@router.get("/{op_id}/contexto", response_model=ContextoOut)
async def get_contexto(op_id: uuid.UUID, session: DbSession):
    """Cartão de contexto. Vazio (existe=false) se sem contexto ou migration 0087 pendente."""
    return await contexto_svc.get_contexto(session, op_id)


@router.put("/{op_id}/contexto", response_model=ContextoOut)
async def put_contexto(
    op_id: uuid.UUID, data: ContextoUpsert, session: DbSession, user_id: CurrentUserId
):
    return await contexto_svc.upsert_contexto(session, user_id, op_id, data)
