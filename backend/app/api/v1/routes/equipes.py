"""Rotas de Equipes (Fatia A · parte 2), prefixo /me/equipes.

Biblioteca do arquiteto (nível-conta, como /me/catalogo). RLS self protege o tenant; aqui só CRUD.
A atribuição da equipe a uma tarefa vai pelo PATCH /obras/{id}/itens/{iid}/detalhes (equipe_id)."""

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUserId, DbSession
from app.schemas.equipes import EquipeCreate, EquipeOut, EquipeUpdate
from app.services import equipes as eq_svc

router = APIRouter()


@router.get("", response_model=list[EquipeOut])
async def listar_equipes(session: DbSession, inativos: bool = Query(default=False)):
    return await eq_svc.listar(session, incluir_inativos=inativos)


@router.post("", response_model=EquipeOut, status_code=status.HTTP_201_CREATED)
async def criar_equipe(data: EquipeCreate, session: DbSession, user_id: CurrentUserId):
    return await eq_svc.criar(session, user_id, data)


@router.patch("/{equipe_id}", response_model=EquipeOut)
async def atualizar_equipe(
    equipe_id: uuid.UUID, data: EquipeUpdate, session: DbSession, user_id: CurrentUserId
):
    return await eq_svc.atualizar(session, user_id, equipe_id, data)


@router.delete("/{equipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_equipe(equipe_id: uuid.UUID, session: DbSession, user_id: CurrentUserId):
    await eq_svc.excluir(session, user_id, equipe_id)
