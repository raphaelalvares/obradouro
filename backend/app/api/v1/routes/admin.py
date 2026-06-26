"""Rotas do painel de admin da plataforma (dono do SaaS).

Plano de autorização SEPARADO do resto da API: todas as rotas (menos GET /admin/me) exigem
is_platform_admin via a dependency abaixo (1ª camada → 403 limpo). As funções SECURITY DEFINER
chamadas pelo service re-checam no banco (2ª camada).
"""

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http

from app.api.deps import DbSession
from app.schemas.admin import (
    AdminMeOut,
    DefinirPlanoIn,
    MetricasAdminOut,
    PlanoCatalogoOut,
    PlanoUpsertIn,
    RenovarPlanoIn,
    TenantAdminOut,
)
from app.services import admin as svc

router = APIRouter()


async def require_platform_admin(session: DbSession) -> None:
    """Gate da API: barra quem não é admin da plataforma antes de qualquer trabalho."""
    if not await svc.is_admin(session):
        raise HTTPException(http.HTTP_403_FORBIDDEN, "acesso restrito ao admin da plataforma")


AdminGuard = Depends(require_platform_admin)


@router.get("/me", response_model=AdminMeOut)
async def admin_me(session: DbSession):
    """SEM gate: todo logado chama; o front usa pra mostrar/esconder o menu Admin."""
    return AdminMeOut(is_admin=await svc.is_admin(session))


@router.get("/tenants", response_model=list[TenantAdminOut], dependencies=[AdminGuard])
async def listar_tenants(session: DbSession):
    return await svc.listar_tenants(session)


@router.get("/metricas", response_model=MetricasAdminOut, dependencies=[AdminGuard])
async def metricas(session: DbSession):
    tenants = await svc.listar_tenants(session)
    planos = await svc.listar_planos(session)
    precos = {p["codigo"]: (p.get("preco_mensal") or 0) for p in planos}
    return svc.metricas(tenants, precos, dt.datetime.now(dt.UTC))


@router.post("/tenants/{tenant_id}/plano", status_code=http.HTTP_204_NO_CONTENT,
             dependencies=[AdminGuard])
async def definir_plano(tenant_id: uuid.UUID, data: DefinirPlanoIn, session: DbSession):
    await svc.definir_plano(session, str(tenant_id), data.plano, data.meses, data.observacao)


@router.post("/tenants/{tenant_id}/renovar", status_code=http.HTTP_204_NO_CONTENT,
             dependencies=[AdminGuard])
async def renovar_plano(tenant_id: uuid.UUID, data: RenovarPlanoIn, session: DbSession):
    await svc.renovar(session, str(tenant_id), data.meses)


@router.delete("/tenants/{tenant_id}/plano", status_code=http.HTTP_204_NO_CONTENT,
               dependencies=[AdminGuard])
async def revogar_plano(tenant_id: uuid.UUID, session: DbSession):
    await svc.revogar(session, str(tenant_id))


@router.get("/planos", response_model=list[PlanoCatalogoOut], dependencies=[AdminGuard])
async def listar_planos(session: DbSession):
    return await svc.listar_planos(session)


@router.put("/planos/{codigo}", status_code=http.HTTP_204_NO_CONTENT, dependencies=[AdminGuard])
async def upsert_plano(codigo: str, data: PlanoUpsertIn, session: DbSession):
    await svc.upsert_plano(session, codigo, data.model_dump())
