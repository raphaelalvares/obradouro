"""Rotas do Acompanhamento (Fatia C), prefixo /obras: diário de obra, pendências (punch list) e o
avanço físico / curva S (derivado do checklist)."""

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUserId, DbSession
from app.schemas.acompanhamento import (
    AvancoOut,
    DiarioCreate,
    DiarioOut,
    DiarioUpdate,
    PendenciaCreate,
    PendenciaOut,
    PendenciaUpdate,
)
from app.schemas.funcoes import FuncaoSimples
from app.services import acompanhamento as acomp_svc
from app.services import diario as diario_svc
from app.services import funcoes as funcoes_svc
from app.services import pendencias as pend_svc

router = APIRouter()


# ============================ funções (picker do efetivo no diário) ============================
@router.get("/{obra_id}/funcoes", response_model=list[FuncaoSimples])
async def listar_funcoes_obra(obra_id: uuid.UUID, session: DbSession):
    """Funções ATIVAS do dono da obra p/ o efetivo do diário (arquiteto e prestador veem)."""
    return await funcoes_svc.listar_da_obra(session, obra_id)


# ============================ diário de obra ============================
@router.get("/{obra_id}/diario", response_model=list[DiarioOut])
async def listar_diario(obra_id: uuid.UUID, session: DbSession):
    return await diario_svc.listar(session, obra_id)


@router.post("/{obra_id}/diario", response_model=DiarioOut, status_code=status.HTTP_201_CREATED)
async def criar_diario(
    obra_id: uuid.UUID, data: DiarioCreate, session: DbSession, user_id: CurrentUserId
):
    return await diario_svc.criar(session, user_id, obra_id, data)


@router.patch("/{obra_id}/diario/{diario_id}", response_model=DiarioOut)
async def atualizar_diario(
    obra_id: uuid.UUID,
    diario_id: uuid.UUID,
    data: DiarioUpdate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await diario_svc.atualizar(session, user_id, obra_id, diario_id, data)


@router.delete("/{obra_id}/diario/{diario_id}")
async def excluir_diario(
    obra_id: uuid.UUID, diario_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await diario_svc.excluir(session, user_id, obra_id, diario_id)


# ============================ pendências / punch list ============================
@router.get("/{obra_id}/pendencias", response_model=list[PendenciaOut])
async def listar_pendencias(
    obra_id: uuid.UUID,
    session: DbSession,
    status_filtro: str | None = Query(default=None, alias="status"),
):
    return await pend_svc.listar(session, obra_id, status_filtro)


@router.post(
    "/{obra_id}/pendencias", response_model=PendenciaOut, status_code=status.HTTP_201_CREATED
)
async def criar_pendencia(
    obra_id: uuid.UUID, data: PendenciaCreate, session: DbSession, user_id: CurrentUserId
):
    return await pend_svc.criar(session, user_id, obra_id, data)


@router.patch("/{obra_id}/pendencias/{pend_id}", response_model=PendenciaOut)
async def atualizar_pendencia(
    obra_id: uuid.UUID,
    pend_id: uuid.UUID,
    data: PendenciaUpdate,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await pend_svc.atualizar(session, user_id, obra_id, pend_id, data)


@router.delete("/{obra_id}/pendencias/{pend_id}")
async def excluir_pendencia(
    obra_id: uuid.UUID, pend_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await pend_svc.excluir(session, user_id, obra_id, pend_id)


# ============================ avanço físico / curva S ============================
@router.get("/{obra_id}/acompanhamento/avanco", response_model=AvancoOut)
async def avanco(obra_id: uuid.UUID, session: DbSession):
    return await acomp_svc.avanco(session, obra_id)
