"""Rotas de cobrança (Fase 9 — Stripe).

`router` (montado em /me) = ações autenticadas do arquiteto. `webhook_router` (montado em /cobranca)
= callback server-to-server do Stripe: SEM JWT, lê o corpo BRUTO + o header de assinatura (a
verificação exige os bytes exatos), e cria a própria sessão de DB no service.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi import status as http

from app.api.deps import Claims, CurrentUserId, DbSession
from app.schemas.cobranca import (
    CheckoutIn,
    CheckoutOut,
    CobrancaStatusOut,
    PlanoAssinavelOut,
)
from app.services import cobranca as svc

router = APIRouter()
webhook_router = APIRouter()

# M6: o payload de webhook do Stripe é pequeno (KBs). Capa o corpo ANTES de ler — endpoint sem JWT,
# não pode virar vetor de DoS de memória. (O middleware global também limita; aqui é o teto justo.)
_WEBHOOK_MAX_BYTES = 1024 * 1024  # 1 MB


@router.get("/cobranca", response_model=CobrancaStatusOut)
async def status(session: DbSession):
    return await svc.status(session)


@router.get("/cobranca/planos", response_model=list[PlanoAssinavelOut])
async def planos(session: DbSession):
    """Catálogo assinável (multi-plano) — o front monta o seletor de planos."""
    return await svc.planos_assinaveis(session)


@router.post("/cobranca/checkout", response_model=CheckoutOut)
async def checkout(
    session: DbSession,
    user_id: CurrentUserId,
    claims: Claims,
    data: CheckoutIn | None = None,
):
    plano = data.plano if data else None
    url = await svc.criar_checkout(session, user_id, claims.get("email"), plano)
    return {"url": url}


@router.post("/cobranca/portal", response_model=CheckoutOut)
async def portal(session: DbSession, user_id: CurrentUserId):
    url = await svc.criar_portal(session, user_id)
    return {"url": url}


@router.post("/cobranca/cancelar", response_model=CobrancaStatusOut)
async def cancelar(session: DbSession, user_id: CurrentUserId):
    """Agenda o cancelamento p/ o fim do período pago (mantém o acesso até lá)."""
    return await svc.cancelar_assinatura(session, user_id)


@router.post("/cobranca/reativar", response_model=CobrancaStatusOut)
async def reativar(session: DbSession, user_id: CurrentUserId):
    """Desfaz o cancelamento agendado (volta a renovar)."""
    return await svc.reativar_assinatura(session, user_id)


@webhook_router.post("/webhook")
async def webhook(request: Request):
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > _WEBHOOK_MAX_BYTES:
                raise HTTPException(http.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "payload muito grande")
        except ValueError:
            pass
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    return await svc.processar_webhook(payload, sig)
