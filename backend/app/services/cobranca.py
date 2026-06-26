"""Serviço de cobrança (Fase 9 — Stripe). MÓDULO SEPARADO do controle de plano (§5): aqui só os
fatos de billing; o webhook traduz o estado da assinatura → plano_codigo (tenant_assinaturas).

Caminho canônico de SaaS: Stripe **Checkout** (página hospedada, PCI leve) p/ assinar + **Customer
Portal** (hospedado) p/ gerenciar/cancelar + **webhooks** p/ refletir o estado no nosso banco. O
webhook é a FONTE DA VERDADE do plano (nunca confiar no redirect de sucesso).

Billing v2 (0091): MULTI-PLANO (cada plano pago → um Stripe Price; o webhook resolve o plano pelo
price, não mais hardcode 'pro') + LEDGER de pagamentos (invoice.payment_succeeded → valor/data) +
HISTÓRICO de planos (registrado dentro de cobranca_aplicar).

Degrada com graça: sem STRIPE_SECRET_KEY/STRIPE_PRICE_PRO o app segue normal e os endpoints de
cobrança respondem 503 "não configurada". `status()`/`planos_assinaveis()` funcionam sem Stripe.
"""

import datetime as dt
import json

import stripe
from fastapi import HTTPException
from fastapi import status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal

settings = get_settings()

# status do Stripe que mantêm o acesso pago (past_due = período de graça antes de cancelar de fato).
_STATUS_PRO = {"active", "trialing", "past_due"}


def _client():
    if not settings.cobranca_configurada:
        raise HTTPException(http.HTTP_503_SERVICE_UNAVAILABLE, "cobrança não configurada")
    stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()
    return stripe


# ============================ leitura (UI) ============================
def _jsonb(v: object) -> dict:
    """asyncpg devolve jsonb como texto; normaliza p/ dict."""
    if isinstance(v, str):
        return json.loads(v) or {}
    return v or {}


async def planos_assinaveis(session: AsyncSession) -> list[dict]:
    """Catálogo que o arquiteto pode assinar (ativos com Stripe Price). Não chama o Stripe."""
    rows = (
        await session.execute(text("select * from public.planos_assinaveis()"))
    ).mappings()
    return [
        {**dict(r), "limites": _jsonb(r["limites"]), "flags": _jsonb(r["flags"])} for r in rows
    ]


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
    pag = (
        await session.execute(
            text(
                "select pago_em, valor_cents from public.cobranca_pagamentos "
                "where tenant_id = (select auth.uid()) order by pago_em desc limit 1"
            )
        )
    ).first()
    assinante_desde = (
        await session.execute(
            text(
                "select min(inicio) from public.tenant_plano_historico "
                "where tenant_id = (select auth.uid()) and plano_codigo <> 'free'"
            )
        )
    ).scalar()
    tem = bool(row and row.stripe_subscription_id and (row.status in _STATUS_PRO))
    return {
        "configurado": settings.cobranca_configurada,
        "plano": plano,
        "status": row.status if row else None,
        "current_period_end": row.current_period_end if row else None,
        "tem_assinatura": tem,
        "assinante_desde": assinante_desde,
        "ultimo_pagamento_em": pag.pago_em if pag else None,
        "ultimo_pagamento_cents": pag.valor_cents if pag else None,
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


async def _price_do_plano(session: AsyncSession, plano: str | None) -> str:
    """Stripe Price do plano escolhido. Sem plano → fallback no STRIPE_PRICE_PRO (env legado).
    400 se o plano não for assinável (sem price)."""
    if not plano:
        return settings.STRIPE_PRICE_PRO
    price = (
        await session.execute(
            text("select stripe_price_id from public.planos where codigo = :c and ativo"),
            {"c": plano},
        )
    ).scalar()
    if not price:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "plano indisponível para assinatura")
    return price


async def criar_checkout(
    session: AsyncSession, user_id: str, email: str | None, plano: str | None = None
) -> str:
    """Sessão de Checkout (assinatura). Retorna a URL hospedada p/ redirecionar."""
    _client()
    price = await _price_do_plano(session, plano)
    customer = await _customer_id(session, user_id, email)
    base = settings.app_base_url
    sess = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer,
        line_items=[{"price": price, "quantity": 1}],
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
def _ts(epoch: int | None) -> dt.datetime | None:
    return dt.datetime.fromtimestamp(epoch, tz=dt.UTC) if epoch else None


def _price_id_sub(obj: dict) -> str | None:
    itens = ((obj.get("items") or {}).get("data")) or []
    return ((itens[0].get("price") or {}).get("id")) if itens else None


def _price_id_invoice(obj: dict) -> str | None:
    linhas = ((obj.get("lines") or {}).get("data")) or []
    return ((linhas[0].get("price") or {}).get("id")) if linhas else None


def mapear_evento(event: dict) -> dict | None:
    """PURA: traduz um evento do Stripe num dict discriminado por `kind` ('subscription' |
    'checkout' | 'payment') ou None se irrelevante. Não resolve plano/tenant que dependam do banco —
    isso fica em `_aplicar` (que tem sessão). tenant_id vem do metadata do checkout (confiável)."""
    tipo = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}

    if tipo.startswith("customer.subscription."):
        meta = obj.get("metadata") or {}
        tenant = meta.get("tenant_id")
        if not tenant:
            return None
        st = "canceled" if tipo.endswith(".deleted") else obj.get("status")
        return {
            "kind": "subscription",
            "tenant_id": tenant,
            "customer": obj.get("customer"),
            "subscription": obj.get("id"),
            "status": st,
            "period_end": _ts(obj.get("current_period_end")),
            "price_id": _price_id_sub(obj),
        }

    if tipo == "checkout.session.completed":
        tenant = (obj.get("metadata") or {}).get("tenant_id") or obj.get("client_reference_id")
        if not tenant:
            return None
        # confirma o customer/subscription; o plano real vem nos eventos de subscription seguintes.
        return {
            "kind": "checkout",
            "tenant_id": tenant,
            "customer": obj.get("customer"),
            "subscription": obj.get("subscription"),
        }

    if tipo in ("invoice.payment_succeeded", "invoice.paid"):
        cents = obj.get("amount_paid")
        if not cents:  # 0/None (ex.: fatura de trial sem cobrança) → nada a registrar
            return None
        meta = (obj.get("subscription_details") or {}).get("metadata") or {}
        paid_at = (obj.get("status_transitions") or {}).get("paid_at") or obj.get("created")
        return {
            "kind": "payment",
            "tenant_id": meta.get("tenant_id"),  # pode faltar → resolve por customer no banco
            "customer": obj.get("customer"),
            "invoice_id": obj.get("id"),
            "amount_cents": cents,
            "currency": obj.get("currency") or "brl",
            "paid_at": _ts(paid_at),
            "price_id": _price_id_invoice(obj),
        }

    return None


async def _plano_por_price(session: AsyncSession, price_id: str | None) -> str | None:
    if not price_id:
        return None
    return (
        await session.execute(
            text("select public.plano_por_price(:p)"), {"p": price_id}
        )
    ).scalar()


async def _aplicar(session: AsyncSession, dados: dict) -> None:
    """Aplica o evento já traduzido no banco (resoluções que dependem do DB ficam aqui)."""
    kind = dados["kind"]

    if kind == "payment":
        plano = await _plano_por_price(session, dados.get("price_id"))
        await session.execute(
            text(
                "select public.cobranca_registrar_pagamento("
                "cast(:t as uuid), :cust, :inv, :cents, :moeda, :plano, :pago)"
            ),
            {
                "t": dados["tenant_id"],
                "cust": dados["customer"],
                "inv": dados["invoice_id"],
                "cents": dados["amount_cents"],
                "moeda": dados["currency"],
                "plano": plano,
                "pago": dados["paid_at"],
            },
        )
        return

    if kind == "subscription":
        st = dados["status"]
        if st in _STATUS_PRO:
            plano = await _plano_por_price(session, dados.get("price_id")) or "pro"
        else:
            plano = "free"
        period_end = dados.get("period_end")
    else:  # checkout: só confirma customer/subscription; plano vem nos eventos de subscription
        st = None
        plano = None
        period_end = None

    await session.execute(
        text("select public.cobranca_aplicar(cast(:t as uuid), :c, :s, :st, :pe, :pl)"),
        {
            "t": dados["tenant_id"],
            "c": dados["customer"],
            "s": dados["subscription"],
            "st": st,
            "pe": period_end,
            "pl": plano,
        },
    )


async def processar_webhook(payload: bytes, sig: str | None) -> dict:
    """Verifica a assinatura, traduz o evento e aplica no banco (via funções SECURITY DEFINER, fora
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
            await _aplicar(session, dados)
    return {"ok": True}
