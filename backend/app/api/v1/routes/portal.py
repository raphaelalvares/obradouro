"""Portal do Cliente: o arquiteto gerencia o acesso (e-mail + prazo) no projeto/obra; o cliente
sincroniza no 1º login. Caminhos mistos (/projetos|/obras do arquiteto, /portal/* do cliente) →
router sem prefixo (registrado direto), como projeto_vinculo."""

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUserId, DbSession
from app.schemas.portal import (
    AcessoClienteCreate,
    AcessoClienteOut,
    AcessoPrazo,
    PortalContextoOut,
)
from app.services import portal as portal_svc

router = APIRouter()


# ---- arquiteto: acesso do cliente (na "área pra colocar o e-mail" do projeto) ----
@router.post(
    "/projetos/{projeto_id}/acessos", response_model=AcessoClienteOut, tags=["portal"]
)
async def autorizar(
    projeto_id: uuid.UUID, data: AcessoClienteCreate, session: DbSession, user_id: CurrentUserId
):
    return await portal_svc.autorizar_acesso(
        session, user_id, projeto_id, data.email, data.validade_tipo, data.validade_ate
    )


@router.get(
    "/projetos/{projeto_id}/acessos", response_model=list[AcessoClienteOut], tags=["portal"]
)
async def listar(projeto_id: uuid.UUID, session: DbSession):
    return await portal_svc.listar_acessos(session, projeto_id)


@router.patch(
    "/projetos/{projeto_id}/acessos/{acesso_id}", response_model=AcessoClienteOut, tags=["portal"]
)
async def definir_prazo(
    projeto_id: uuid.UUID,
    acesso_id: uuid.UUID,
    data: AcessoPrazo,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await portal_svc.definir_prazo_acesso(
        session, user_id, projeto_id, acesso_id, data.validade_tipo, data.validade_ate
    )


@router.delete("/projetos/{projeto_id}/acessos/{acesso_id}", tags=["portal"])
async def revogar(
    projeto_id: uuid.UUID, acesso_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await portal_svc.revogar_acesso(session, user_id, projeto_id, acesso_id)


# ---- arquiteto: acesso do cliente direto numa obra (sem projeto) ----
@router.post("/obras/{obra_id}/acessos", response_model=AcessoClienteOut, tags=["portal"])
async def autorizar_obra(
    obra_id: uuid.UUID, data: AcessoClienteCreate, session: DbSession, user_id: CurrentUserId
):
    return await portal_svc.autorizar_acesso_obra(
        session, user_id, obra_id, data.email, data.validade_tipo, data.validade_ate
    )


@router.get("/obras/{obra_id}/acessos", response_model=list[AcessoClienteOut], tags=["portal"])
async def listar_obra(obra_id: uuid.UUID, session: DbSession):
    return await portal_svc.listar_acessos_obra(session, obra_id)


@router.patch(
    "/obras/{obra_id}/acessos/{acesso_id}", response_model=AcessoClienteOut, tags=["portal"]
)
async def definir_prazo_obra(
    obra_id: uuid.UUID,
    acesso_id: uuid.UUID,
    data: AcessoPrazo,
    session: DbSession,
    user_id: CurrentUserId,
):
    return await portal_svc.definir_prazo_acesso_obra(
        session, user_id, obra_id, acesso_id, data.validade_tipo, data.validade_ate
    )


@router.delete("/obras/{obra_id}/acessos/{acesso_id}", tags=["portal"])
async def revogar_obra(
    obra_id: uuid.UUID, acesso_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
):
    return await portal_svc.revogar_acesso_obra(session, user_id, obra_id, acesso_id)


# ---- cliente: reconcilia o e-mail confirmado e devolve o contexto de roteamento ----
@router.post("/portal/sincronizar", response_model=PortalContextoOut, tags=["portal"])
async def sincronizar(session: DbSession):
    return await portal_svc.sincronizar(session)
