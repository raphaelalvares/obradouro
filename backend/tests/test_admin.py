"""Testes do painel de admin da plataforma.

Sem banco: (a) gate de auth nas rotas /admin/* (401/403 antes de tocar no DB); (b) presença das
rotas no OpenAPI; (c) unit da métrica PURA (contagens, expiração, receita).
"""

import datetime as dt

from fastapi.testclient import TestClient

from app.main import app
from app.services.admin import metricas

client = TestClient(app)

AGORA = dt.datetime(2026, 6, 26, tzinfo=dt.UTC)
TENANT = "00000000-0000-0000-0000-000000000000"


# --------------------------------------------------------------------- gate de auth
def test_admin_routes_require_auth():
    for method, path in [
        ("get", "/api/v1/admin/me"),
        ("get", "/api/v1/admin/tenants"),
        ("get", "/api/v1/admin/metricas"),
        ("get", "/api/v1/admin/planos"),
    ]:
        r = client.request(method, path)
        assert r.status_code in (401, 403), (path, r.status_code)


def test_admin_write_routes_require_auth():
    r1 = client.post(f"/api/v1/admin/tenants/{TENANT}/plano", json={"plano": "pro"})
    r2 = client.post(f"/api/v1/admin/tenants/{TENANT}/renovar", json={"meses": 1})
    r3 = client.delete(f"/api/v1/admin/tenants/{TENANT}/plano")
    assert r1.status_code in (401, 403)
    assert r2.status_code in (401, 403)
    assert r3.status_code in (401, 403)


def test_admin_routes_in_openapi():
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    for p in [
        "/api/v1/admin/me",
        "/api/v1/admin/tenants",
        "/api/v1/admin/metricas",
        "/api/v1/admin/tenants/{tenant_id}/plano",
        "/api/v1/admin/tenants/{tenant_id}/renovar",
        "/api/v1/admin/planos",
        "/api/v1/admin/planos/{codigo}",
    ]:
        assert p in paths, p


# --------------------------------------------------------------------- métrica pura
def _tenant(plano="free", origem=None, expira_em=None, period_end=None):
    return {
        "plano_codigo": plano,
        "origem": origem,
        "expira_em": expira_em,
        "current_period_end": period_end,
    }


PRECOS = {"free": 0, "pro": 49.9}


def test_metricas_conta_total_e_pagantes():
    tenants = [_tenant("free"), _tenant("pro", "manual"), _tenant("pro", "stripe")]
    m = metricas(tenants, PRECOS, AGORA)
    assert m["total_clientes"] == 3
    assert m["pagantes"] == 2
    assert {"plano": "free", "quantidade": 1} in m["por_plano"]
    assert {"plano": "pro", "quantidade": 2} in m["por_plano"]


def test_metricas_receita_soma_so_pagantes():
    tenants = [_tenant("free"), _tenant("pro", "manual"), _tenant("pro", "manual")]
    m = metricas(tenants, PRECOS, AGORA)
    assert m["receita_mensal_estimada"] == 99.8


def test_metricas_expirando_usa_data_relevante_por_origem():
    d = dt.timedelta
    tenants = [
        _tenant("pro", "manual", expira_em=AGORA + d(days=5)),  # 5d → conta em 7d e 30d
        _tenant("pro", "manual", expira_em=AGORA + d(days=20)),  # só 30d
        _tenant("pro", "stripe", period_end=AGORA + d(days=3)),  # stripe usa period_end
        _tenant("pro", "manual", expira_em=None),  # sem expiração → não conta
        _tenant("pro", "manual", expira_em=AGORA - d(days=1)),  # já expirou → não conta
    ]
    m = metricas(tenants, PRECOS, AGORA)
    assert m["expirando_7d"] == 2  # o manual de 5d + o stripe de 3d
    assert m["expirando_30d"] == 3  # +o manual de 20d


def test_metricas_vazio():
    m = metricas([], PRECOS, AGORA)
    assert m["total_clientes"] == 0
    assert m["pagantes"] == 0
    assert m["receita_mensal_estimada"] == 0
    assert m["por_plano"] == []
