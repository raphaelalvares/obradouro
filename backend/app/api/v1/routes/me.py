"""Rotas do perfil do usuário corrente."""

from fastapi import APIRouter

from app.api.deps import Claims, DbSession
from app.schemas.me import ProfileOut, ProfileUpdate
from app.schemas.planos import QuotaOut
from app.services import me as me_svc
from app.services import planos as planos_svc

router = APIRouter()


@router.get("", response_model=ProfileOut)
async def read_me(session: DbSession, claims: Claims):
    return await me_svc.get_or_create_me(session, claims.get("email"))


@router.patch("", response_model=ProfileOut)
async def patch_me(data: ProfileUpdate, session: DbSession, claims: Claims):
    return await me_svc.update_me(session, claims.get("email"), data)


@router.get("/quota", response_model=QuotaOut)
async def quota(session: DbSession):
    return await planos_svc.get_quota(session)
