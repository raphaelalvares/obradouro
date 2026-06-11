"""Rotas de Funções/cargos (Fatia C), prefixo /me/funcoes.

Biblioteca do arquiteto (nível-conta, como /me/equipes). RLS self protege o tenant; aqui só CRUD. O
picker por obra (usado no diário, inclusive pelo prestador) vive em GET /obras/{id}/funcoes."""

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUserId, DbSession
from app.schemas.funcoes import FuncaoCreate, FuncaoOut, FuncaoUpdate
from app.services import funcoes as fn_svc

router = APIRouter()


@router.get("", response_model=list[FuncaoOut])
async def listar_funcoes(session: DbSession, inativos: bool = Query(default=False)):
    return await fn_svc.listar(session, incluir_inativos=inativos)


@router.post("", response_model=FuncaoOut, status_code=status.HTTP_201_CREATED)
async def criar_funcao(data: FuncaoCreate, session: DbSession, user_id: CurrentUserId):
    return await fn_svc.criar(session, user_id, data)


@router.patch("/{funcao_id}", response_model=FuncaoOut)
async def atualizar_funcao(
    funcao_id: uuid.UUID, data: FuncaoUpdate, session: DbSession, user_id: CurrentUserId
):
    return await fn_svc.atualizar(session, user_id, funcao_id, data)


@router.delete("/{funcao_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_funcao(funcao_id: uuid.UUID, session: DbSession, user_id: CurrentUserId):
    await fn_svc.excluir(session, user_id, funcao_id)
