"""Rotas do Catálogo de serviços (Livro de referências · Fatia 1), prefixo /me/catalogo.

Biblioteca do arquiteto (nível-conta, como /me/branding). RLS self protege o tenant; aqui só CRUD +
'promover' (salvar no catálogo a partir de uma linha de orçamento, com a divisão subtotal→unitário
feita no service)."""

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUserId, DbSession
from app.schemas.catalogo import (
    PromoverServicoIn,
    ServicoCreate,
    ServicoOut,
    ServicoPromovidoOut,
    ServicoUpdate,
)
from app.services import catalogo as cat_svc

router = APIRouter()


@router.get("", response_model=list[ServicoOut])
async def listar_servicos(session: DbSession, inativos: bool = Query(default=False)):
    return await cat_svc.listar(session, incluir_inativos=inativos)


@router.post("", response_model=ServicoOut, status_code=status.HTTP_201_CREATED)
async def criar_servico(data: ServicoCreate, session: DbSession, user_id: CurrentUserId):
    return await cat_svc.criar(session, user_id, data)


# rota ESTÁTICA antes da paramétrica (/promover não pode cair em /{servico_id}).
@router.post("/promover", response_model=ServicoPromovidoOut)
async def promover_servico(data: PromoverServicoIn, session: DbSession, user_id: CurrentUserId):
    return await cat_svc.promover(session, user_id, data)


@router.patch("/{servico_id}", response_model=ServicoOut)
async def atualizar_servico(
    servico_id: uuid.UUID, data: ServicoUpdate, session: DbSession, user_id: CurrentUserId
):
    return await cat_svc.atualizar(session, user_id, servico_id, data)


@router.delete("/{servico_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir_servico(servico_id: uuid.UUID, session: DbSession, user_id: CurrentUserId):
    await cat_svc.excluir(session, user_id, servico_id)
