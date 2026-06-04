"""Serviço de cobrança (Fase 9 — Stripe). MÓDULO SEPARADO do controle de plano (§5): aqui só os
fatos de billing; o webhook traduz o estado da assinatura → plano_codigo (tenant_assinaturas).

Caminho canônico de SaaS: Stripe **Checkout** (página hospedada, PCI leve) p/ assinar + **Customer
Portal** (hospedado) p/ gerenciar/cancelar + **webhooks** p/ refletir o estado no nosso banco. O
webhook é a FONTE DA VERDADE do plano (nunca confiar no redirect de sucesso).

Degrada com graça: sem STRIPE_SECRET_KEY/STRIPE_PRICE_PRO o app segue normal e os endpoints de
cobrança respondem 503 "não configurada". `status()` funciona sem Stripe (só lê o banco).
"""

import datetime as dt

import stripe
from fastapi import HTTPException
from fastapi import status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal

settings = get_settings()

# status do Stripe que mantêm o acesso Pro (past_due = período de graça antes de cancelar de fato).
_STATUS_PRO = {"active", "trialing", "past_due"}


def _client():
    if not settings.cobranca_configurada:
        raise HTTPException(http.HTTP_503_SERVICE_UNAVAILABLE, "cobrança não configurada")
    stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()
    return stripe


# ============================ leitura (UI) ============================
async def status(session: AsyncSession) -> dict:
    """Status p/ a tela de conta (não chama o Stripe — só o banco)."""
    plano = (
        await session.execute(
            text("select codigo from public.plano_do_tenant((select auth.uid()))")
        )
    ).scalar() or "free"
    row = (
        await session.execute(
            text(
                "select status, current_period_end, stripe_subscription_id "
                "from public.tenant_cobranca where tenant_id = (select auth.uid())"
            )
        )
    ).first()
    tem = bool(row and row.stripe_subscription_id and (row.status in _STATUS_PRO))
    return {
        "configurado": settings.cobranca_configurada,
        "plano": plano,
        "status": row.status if row else None,
        "current_period_end": row.current_period_end if row else None,
        "tem_assinatura": tem,
    }


# ============================ Checkout / Portal ============================
async def _customer_id(session: AsyncSession, user_id: str, email: str | None) -> str:
    """Customer do Stripe do tenant (cria na 1ª vez e guarda). metadata.tenant_id liga de volta."""
    existente = (
        await session.execute(
            text(
                "select stripe_customer_id from public.tenant_cobranca "
                "where tenant_id = (select auth.uid())"
            )
        )
    ).scalar()
    if existente:
        return existente
    cust = stripe.Customer.create(email=email, metadata={"tenant_id": user_id})
    await session.execute(
        text("select public.cobranca_set_customer(cast(:t as uuid), :c)"),
        {"t": user_id, "c": cust.id},
    )
    return cust.id


async def criar_checkout(session: AsyncSession, user_id: str, email: str | None) -> str:
    """Sessão de Checkout (assinatura do Pro). Retorna a URL hospedada p/ redirecionar."""
    _client()
    customer = await _customer_id(session, user_id, email)
    base = settings.app_base_url
    sess = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer,
        line_items=[{"price": settings.STRIPE_PRICE_PRO, "quantity": 1}],
        client_reference_id=user_id,
        subscription_data={"metadata": {"tenant_id": user_id}},
        success_url=f"{base}/configuracoes?cobranca=sucesso",
        cancel_url=f"{base}/configuracoes?cobranca=cancelado",
    )
    return sess.url


async def criar_portal(session: AsyncSession, user_id: str) -> str:
    """Sessão do Customer Portal (gerenciar/cancelar). 409 se o tenant ainda não tem customer."""
    _client()
    customer = (
        await session.execute(
            text(
                "select stripe_customer_id from public.tenant_cobranca "
                "where tenant_id = (select auth.uid())"
            )
        )
    ).scalar()
    if not customer:
        raise HTTPException(http.HTTP_409_CONFLICT, "sem assinatura para gerenciar")
    sess = stripe.billing_portal.Session.create(
        customer=customer, return_url=f"{settings.app_base_url}/configuracoes"
    )
    return sess.url


# ============================ Webhook ============================
def _period_end(obj: dict) -> dt.datetime | None:
    ts = obj.get("current_period_end")
    return dt.datetime.fromtimestamp(ts, tz=dt.UTC) if ts else None


def mapear_evento(event: dict) -> dict | None:
    """PURA: traduz um evento do Stripe em {tenant_id, customer, subscription, status, period_end,
    plano} ou None se for irrelevante. `plano` segue o status (Pro enquanto active/trialing/
    past_due; senão free). tenant_id vem do metadata setado no checkout (fonte confiável)."""
    tipo = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}

    if tipo.startswith("customer.subscription."):
        meta = obj.get("metadata") or {}
        tenant = meta.get("tenant_id")
        if not tenant:
            return None
        st = "canceled" if tipo.endswith(".deleted") else obj.get("status")
        plano = "pro" if st in _STATUS_PRO else "free"
        return {
            "tenant_id": tenant,
            "customer": obj.get("customer"),
            "subscription": obj.get("id"),
            "status": st,
            "period_end": _period_end(obj),
            "plano": plano,
        }

    if tipo == "checkout.session.completed":
        tenant = (obj.get("metadata") or {}).get("tenant_id") or obj.get("client_reference_id")
        if not tenant:
            return None
        # confirma o customer/subscription; o plano real vem nos eventos de subscription seguintes.
        return {
            "tenant_id": tenant,
            "customer": obj.get("customer"),
            "subscription": obj.get("subscription"),
            "status": None,
            "period_end": None,
            "plano": None,
        }

    return None


async def processar_webhook(payload: bytes, sig: str | None) -> dict:
    """Verifica a assinatura, traduz o evento e aplica no banco (via função SECURITY DEFINER, fora
    do contexto authenticated). Idempotente: reprocessar o mesmo evento converge ao mesmo estado."""
    if not settings.cobranca_configurada or not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(http.HTTP_503_SERVICE_UNAVAILABLE, "cobrança não configurada")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig or "", settings.STRIPE_WEBHOOK_SECRET.get_secret_value()
        )
    except (ValueError, stripe.SignatureVerificationError) as e:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "assinatura do webhook inválida") from e

    dados = mapear_evento(event if isinstance(event, dict) else event.to_dict_recursive())
    if dados is None:
        return {"ignored": True}

    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(
                text(
                    "select public.cobranca_aplicar(cast(:t as uuid), :c, :s, :st, :pe, :pl)"
                ),
                {
                    "t": dados["tenant_id"],
                    "c": dados["customer"],
                    "s": dados["subscription"],
                    "st": dados["status"],
                    "pe": dados["period_end"],
                    "pl": dados["plano"],
                },
            )
    return {"ok": True}
