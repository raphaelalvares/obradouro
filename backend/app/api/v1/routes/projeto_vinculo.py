"""Vínculo do projeto no nível raiz: inscrições pendentes, aceitar convite, resgatar código.
Caminhos /projeto-* para não colidir com /projetos/{id}."""

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUserId, DbSession
from app.schemas.projetos import (
    AceiteProjetoOut,
    ProjetoPendenteOut,
    ResgatarProjetoCodigo,
    ResgateProjetoOut,
)
from app.services import projeto_vinculo as vinc_svc

router = APIRouter()


@router.get("/me/projetos-pendentes", response_model=list[ProjetoPendenteOut], tags=["me"])
async def projetos_pendentes(session: DbSession):
    return await vinc_svc.listar_pendentes(session)


@router.post(
    "/projeto-convites/{membro_id}/aceitar", response_model=AceiteProjetoOut, tags=["projetos"]
)
async def aceitar(membro_id: uuid.UUID, session: DbSession, user_id: CurrentUserId):
    return await vinc_svc.aceitar_convite(session, user_id, membro_id)


@router.post("/projeto-codigo/resgatar", response_model=ResgateProjetoOut, tags=["projetos"])
async def resgatar(data: ResgatarProjetoCodigo, session: DbSession):
    return await vinc_svc.resgatar(session, data.codigo)
