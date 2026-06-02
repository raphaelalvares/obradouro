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
    assert "/api/v1/me" in paths
    assert "/api/v1/obras" in paths
    assert "/api/v1/obras/{obra_id}/arquivar" in paths
    assert "/api/v1/obras/{obra_id}/audit" in paths
