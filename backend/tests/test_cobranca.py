"""Testes do mapeamento de eventos do Stripe (Fase 9 / billing v2) — puro, sem chamar o Stripe.

Billing v2: mapear_evento é PURO e devolve um dict discriminado por `kind`. A resolução plano↔price
e o status→pro/free dependem do banco e ficam em _aplicar (não testado aqui — exige sessão)."""

import datetime as dt

from app.services.cobranca import mapear_evento

TENANT = "11111111-1111-1111-1111-111111111111"


def _sub_event(
    tipo: str,
    status_sub: str,
    *,
    com_tenant: bool = True,
    price: str = "price_pro",
    cancel_at_period_end: bool = False,
) -> dict:
    return {
        "type": tipo,
        "data": {
            "object": {
                "id": "sub_123",
                "customer": "cus_123",
                "status": status_sub,
                "current_period_end": 1893456000,  # 2030-01-01 UTC
                "cancel_at_period_end": cancel_at_period_end,
                "items": {"data": [{"price": {"id": price}}]},
                "metadata": {"tenant_id": TENANT} if com_tenant else {},
            }
        },
    }


def test_subscription_traduz_status_e_price():
    d = mapear_evento(_sub_event("customer.subscription.updated", "active"))
    assert d["kind"] == "subscription"
    assert d["tenant_id"] == TENANT
    assert d["status"] == "active"
    assert d["price_id"] == "price_pro"
    assert d["subscription"] == "sub_123"
    assert d["customer"] == "cus_123"
    assert d["period_end"] == dt.datetime(2030, 1, 1, tzinfo=dt.UTC)
    assert d["cancel_at_period_end"] is False


def test_subscription_cancelamento_agendado():
    d = mapear_evento(
        _sub_event("customer.subscription.updated", "active", cancel_at_period_end=True)
    )
    assert d["cancel_at_period_end"] is True
    assert d["status"] == "active"  # segue ativo até o fim do período


def test_subscription_deletada_status_canceled():
    d = mapear_evento(_sub_event("customer.subscription.deleted", "active"))
    assert d["kind"] == "subscription"
    assert d["status"] == "canceled"


def test_subscription_multi_plano_carrega_price():
    d = mapear_evento(_sub_event("customer.subscription.updated", "active", price="price_studio"))
    assert d["price_id"] == "price_studio"  # plano resolvido por price no _aplicar (multi-plano)


def test_sem_tenant_id_ignora():
    ev = _sub_event("customer.subscription.updated", "active", com_tenant=False)
    assert mapear_evento(ev) is None


def test_checkout_completed_confirma_sem_plano():
    ev = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_9",
                "subscription": "sub_9",
                "client_reference_id": TENANT,
                "metadata": {},
            }
        },
    }
    d = mapear_evento(ev)
    assert d["kind"] == "checkout"
    assert d["tenant_id"] == TENANT
    assert d["customer"] == "cus_9"


def test_invoice_pago_vira_pagamento():
    ev = {
        "type": "invoice.payment_succeeded",
        "data": {
            "object": {
                "id": "in_777",
                "customer": "cus_123",
                "amount_paid": 4990,
                "currency": "brl",
                "status_transitions": {"paid_at": 1893456000},
                "lines": {"data": [{"price": {"id": "price_pro"}}]},
                "subscription_details": {"metadata": {"tenant_id": TENANT}},
            }
        },
    }
    d = mapear_evento(ev)
    assert d["kind"] == "payment"
    assert d["tenant_id"] == TENANT
    assert d["invoice_id"] == "in_777"
    assert d["amount_cents"] == 4990
    assert d["currency"] == "brl"
    assert d["price_id"] == "price_pro"
    assert d["paid_at"] == dt.datetime(2030, 1, 1, tzinfo=dt.UTC)


def test_invoice_sem_valor_ignora():
    ev = {"type": "invoice.payment_succeeded", "data": {"object": {"amount_paid": 0}}}
    assert mapear_evento(ev) is None


def test_evento_irrelevante_ignora():
    assert mapear_evento({"type": "customer.updated", "data": {"object": {}}}) is None
