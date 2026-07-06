"""Testes de rota sem banco: gate de autenticação e presença das rotas no OpenAPI."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_protected_routes_require_auth():
    # Sem Authorization, o HTTPBearer nega antes de tocar no banco.
    for method, path in [("get", "/api/v1/me"), ("get", "/api/v1/obras")]:
        r = client.request(method, path)
        assert r.status_code in (401, 403), (path, r.status_code)


def test_openapi_lists_phase1_routes():
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    for p in [
        "/api/v1/me",
        "/api/v1/me/quota",
        "/api/v1/obras",
        "/api/v1/obras/{obra_id}/arquivar",
        "/api/v1/obras/{obra_id}/audit",
        # Fase 3 (checklist)
        "/api/v1/obras/{obra_id}/checklist",
        "/api/v1/obras/{obra_id}/etapas",
        "/api/v1/obras/{obra_id}/etapas/{etapa_id}",
        "/api/v1/obras/{obra_id}/etapas/{etapa_id}/ordem",
        "/api/v1/obras/{obra_id}/itens",
        "/api/v1/obras/{obra_id}/itens/{item_id}",
        "/api/v1/obras/{obra_id}/itens/{item_id}/estado",
        "/api/v1/obras/{obra_id}/checklist/importar",
    ]:
        assert p in paths, p


def test_acesso_cliente_route_requires_auth():
    # O acesso do cliente é concedido só pelo Portal (unificação — migration 0103).
    r = client.get("/api/v1/projetos/00000000-0000-0000-0000-000000000000/acessos")
    assert r.status_code in (401, 403)
