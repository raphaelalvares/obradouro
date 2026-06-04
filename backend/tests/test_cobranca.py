"""Testes do mapeamento de eventos do Stripe (Fase 9) — puro, sem chamar o Stripe."""

import datetime as dt

from app.services.cobranca import mapear_evento

TENANT = "11111111-1111-1111-1111-111111111111"


def _sub_event(tipo: str, status_sub: str, *, com_tenant: bool = True) -> dict:
    return {
        "type": tipo,
        "data": {
            "object": {
                "id": "sub_123",
                "customer": "cus_123",
                "status": status_sub,
                "current_period_end": 1893456000,  # 2030-01-01 UTC
                "metadata": {"tenant_id": TENANT} if com_tenant else {},
            }
        },
    }


def test_subscription_ativa_vira_pro():
    d = mapear_evento(_sub_event("customer.subscription.updated", "active"))
    assert d["tenant_id"] == TENANT
    assert d["plano"] == "pro"
    assert d["status"] == "active"
    assert d["subscription"] == "sub_123"
    assert d["customer"] == "cus_123"
    assert d["period_end"] == dt.datetime(2030, 1, 1, tzinfo=dt.UTC)


def test_past_due_mantem_pro_periodo_de_graca():
    d = mapear_evento(_sub_event("customer.subscription.updated", "past_due"))
    assert d["plano"] == "pro"


def test_subscription_deletada_vira_free():
    d = mapear_evento(_sub_event("customer.subscription.deleted", "active"))
    assert d["status"] == "canceled"
    assert d["plano"] == "free"


def test_subscription_cancelada_vira_free():
    d = mapear_evento(_sub_event("customer.subscription.updated", "canceled"))
    assert d["plano"] == "free"


def test_sem_tenant_id_ignora():
    ev = _sub_event("customer.subscription.updated", "active", com_tenant=False)
    assert mapear_evento(ev) is None


def test_checkout_completed_confirma_sem_definir_plano():
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
    assert d["tenant_id"] == TENANT
    assert d["plano"] is None  # o plano vem nos eventos de subscription seguintes
    assert d["customer"] == "cus_9"


def test_evento_irrelevante_ignora():
    assert mapear_evento({"type": "invoice.paid", "data": {"object": {}}}) is None
