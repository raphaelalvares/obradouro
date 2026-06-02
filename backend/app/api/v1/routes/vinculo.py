"""Rotas de vínculo no nível raiz: convites pendentes, aceitar convite e resgatar código."""

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUserId, DbSession
from app.schemas.codigo import ResgatarCodigo, ResgateOut
from app.schemas.convites import AceiteOut, ConvitePendenteOut
from app.services import codigo as codigo_svc
from app.services import convites as convites_svc

router = APIRouter()


@router.get("/me/convites-pendentes", response_model=list[ConvitePendenteOut], tags=["me"])
async def convites_pendentes(session: DbSession):
    return await convites_svc.listar_pendentes(session)


@router.post("/convites/{membro_id}/aceitar", response_model=AceiteOut, tags=["convites"])
async def aceitar(membro_id: uuid.UUID, session: DbSession, user_id: CurrentUserId):
    return await convites_svc.aceitar_convite(session, user_id, membro_id)


@router.post("/codigo/resgatar", response_model=ResgateOut, tags=["convites"])
async def resgatar(data: ResgatarCodigo, session: DbSession):
    return await codigo_svc.resgatar(session, data.codigo)
