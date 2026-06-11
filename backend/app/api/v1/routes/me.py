"""Rotas do perfil do usuário corrente + marca do escritório (Fase 7)."""

from typing import Annotated

from fastapi import APIRouter, File, Response, UploadFile

from app.api.deps import Claims, CurrentUserId, DbSession
from app.schemas.branding import BrandingOut, BrandingUpdate
from app.schemas.me import ProfileOut, ProfileUpdate
from app.schemas.orcamentos import OrcamentoCentralOut
from app.schemas.planos import QuotaOut
from app.services import branding as branding_svc
from app.services import me as me_svc
from app.services import orcamentos as orc_svc
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


@router.get("/orcamentos", response_model=list[OrcamentoCentralOut])
async def central_orcamentos(session: DbSession):
    """Central de orçamentos: visão cross-projeto da versão atual de cada projeto do arquiteto."""
    return await orc_svc.central(session)


# ---------------- marca do escritório (Fase 7 — personalização) ----------------
@router.get("/branding", response_model=BrandingOut)
async def get_branding(session: DbSession):
    return await branding_svc.get_branding(session)


@router.patch("/branding", response_model=BrandingOut)
async def patch_branding(data: BrandingUpdate, session: DbSession, user_id: CurrentUserId):
    return await branding_svc.update_branding(session, user_id, data)


@router.put("/branding/logo", response_model=BrandingOut)
async def put_logo(
    session: DbSession, user_id: CurrentUserId, arquivo: Annotated[UploadFile, File()]
):
    return await branding_svc.upload_logo(session, user_id, arquivo)


@router.get("/branding/logo")
async def get_logo(session: DbSession):
    data, content_type = await branding_svc.serve_logo(session)
    return Response(content=data, media_type=content_type)


@router.delete("/branding/logo", response_model=BrandingOut)
async def delete_logo(session: DbSession, user_id: CurrentUserId):
    return await branding_svc.delete_logo(session, user_id)
