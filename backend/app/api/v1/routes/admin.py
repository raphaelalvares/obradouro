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
    AcessosAdminOut,
    AdminMeOut,
    AuditLogOut,
    AutorizarAcessoIn,
    DefinirPlanoIn,
    MetricasAdminOut,
    NotaCriarIn,
    NotaOut,
    NovosOut,
    PlanoCatalogoOut,
    PlanoUpsertIn,
    RenovarPlanoIn,
    ResetLinkOut,
    SuporteStatusOut,
    TenantAdminOut,
    TenantHistoricoOut,
)
from app.services import admin as svc
from app.services import users as auth_svc

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
    churn = await svc.churn(session, 30)
    return svc.metricas(tenants, precos, dt.datetime.now(dt.UTC), churn)


@router.get("/tenants/{tenant_id}/historico", response_model=TenantHistoricoOut,
            dependencies=[AdminGuard])
async def tenant_historico(tenant_id: uuid.UUID, session: DbSession):
    """Detalhe de billing do cliente: timeline de planos (pro/free) + pagamentos."""
    return TenantHistoricoOut(
        historico=await svc.planos_historico(session, str(tenant_id)),
        pagamentos=await svc.pagamentos(session, str(tenant_id)),
    )


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


# ===================== notificação de novo cadastro =====================
@router.get("/novos", response_model=NovosOut, dependencies=[AdminGuard])
async def novos(session: DbSession):
    return NovosOut(novos=await svc.novos_count(session))


@router.post("/novos/visto", status_code=http.HTTP_204_NO_CONTENT, dependencies=[AdminGuard])
async def marcar_vistos(session: DbSession):
    await svc.marcar_vistos(session)


# ===================== auditoria =====================
@router.get("/log", response_model=list[AuditLogOut], dependencies=[AdminGuard])
async def log(session: DbSession):
    return await svc.log_listar(session, 200)


# ===================== gestão de e-mails de cliente nas obras =====================
@router.get("/tenants/{tenant_id}/acessos", response_model=AcessosAdminOut,
            dependencies=[AdminGuard])
async def listar_acessos(tenant_id: uuid.UUID, session: DbSession):
    return AcessosAdminOut(
        acessos=await svc.listar_acessos(session, str(tenant_id)),
        alvos=await svc.listar_alvos(session, str(tenant_id)),
    )


@router.post("/tenants/{tenant_id}/acessos", status_code=http.HTTP_204_NO_CONTENT,
             dependencies=[AdminGuard])
async def autorizar_acesso(tenant_id: uuid.UUID, data: AutorizarAcessoIn, session: DbSession):
    await svc.autorizar_acesso(
        session,
        str(data.projeto_id) if data.projeto_id else None,
        str(data.obra_id) if data.obra_id else None,
        data.email,
    )


@router.delete("/acessos/{acesso_id}", status_code=http.HTTP_204_NO_CONTENT,
               dependencies=[AdminGuard])
async def revogar_acesso(acesso_id: uuid.UUID, session: DbSession):
    await svc.revogar_acesso(session, str(acesso_id))


# ===================== notas internas =====================
@router.get("/tenants/{tenant_id}/notas", response_model=list[NotaOut], dependencies=[AdminGuard])
async def listar_notas(tenant_id: uuid.UUID, session: DbSession):
    return await svc.notas_listar(session, str(tenant_id))


@router.post("/tenants/{tenant_id}/notas", status_code=http.HTTP_204_NO_CONTENT,
             dependencies=[AdminGuard])
async def criar_nota(tenant_id: uuid.UUID, data: NotaCriarIn, session: DbSession):
    await svc.nota_criar(session, str(tenant_id), data.texto)


@router.delete("/notas/{nota_id}", status_code=http.HTTP_204_NO_CONTENT, dependencies=[AdminGuard])
async def excluir_nota(nota_id: uuid.UUID, session: DbSession):
    await svc.nota_excluir(session, str(nota_id))


# ===================== suporte ao usuário (GoTrue Admin) =====================
@router.get("/tenants/{tenant_id}/suporte", response_model=SuporteStatusOut,
            dependencies=[AdminGuard])
async def suporte_status(tenant_id: uuid.UUID):
    return await auth_svc.status_usuario(str(tenant_id))


@router.post("/tenants/{tenant_id}/suporte/reenviar-confirmacao",
             status_code=http.HTTP_204_NO_CONTENT, dependencies=[AdminGuard])
async def suporte_reenviar(tenant_id: uuid.UUID, session: DbSession):
    await auth_svc.reenviar_confirmacao(str(tenant_id))
    await svc.log(session, "reenviar_confirmacao", str(tenant_id))


@router.post("/tenants/{tenant_id}/suporte/reset-senha", response_model=ResetLinkOut,
             dependencies=[AdminGuard])
async def suporte_reset(tenant_id: uuid.UUID, session: DbSession):
    link = await auth_svc.link_reset_senha(str(tenant_id))
    await svc.log(session, "reset_senha", str(tenant_id))
    return ResetLinkOut(link=link)


@router.post("/tenants/{tenant_id}/suporte/suspender", status_code=http.HTTP_204_NO_CONTENT,
             dependencies=[AdminGuard])
async def suporte_suspender(tenant_id: uuid.UUID, session: DbSession):
    await auth_svc.definir_ban(str(tenant_id), True)
    await svc.log(session, "suspender", str(tenant_id))


@router.post("/tenants/{tenant_id}/suporte/reativar", status_code=http.HTTP_204_NO_CONTENT,
             dependencies=[AdminGuard])
async def suporte_reativar(tenant_id: uuid.UUID, session: DbSession):
    await auth_svc.definir_ban(str(tenant_id), False)
    await svc.log(session, "reativar", str(tenant_id))
