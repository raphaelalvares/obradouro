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
        "/api/v1/obras/{obra_id}/membros",
        "/api/v1/obras/{obra_id}/membros/{membro_id}",
        "/api/v1/obras/{obra_id}/convites",
        "/api/v1/obras/{obra_id}/codigo",
        "/api/v1/me/convites-pendentes",
        "/api/v1/convites/{membro_id}/aceitar",
        "/api/v1/codigo/resgatar",
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


def test_vinculo_routes_require_auth():
    assert client.get("/api/v1/me/convites-pendentes").status_code in (401, 403)
    assert client.get("/api/v1/obras/00000000-0000-0000-0000-000000000000/membros").status_code in (
        401,
        403,
    )
