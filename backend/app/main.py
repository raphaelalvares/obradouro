"""Ponto de entrada da API CRIA (FastAPI)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import assert_safe_db_role, engine
from app.core.middleware import SecurityMiddleware
from app.core.problems import (
    FeatureBloqueadaError,
    LimiteArmazenamentoError,
    LimiteAtivasError,
    feature_bloqueada_handler,
    limite_armazenamento_handler,
    limite_ativas_handler,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: garante que a conexão NÃO faz bypass de RLS (a 2ª camada precisa valer)
    await assert_safe_db_role()
    yield
    # shutdown
    await engine.dispose()


# I1: em produção, NÃO expõe o schema OpenAPI nem o Swagger/ReDoc (reduz a superfície de
# reconhecimento — rotas, schemas, exemplos). Em dev/staging seguem ligados p/ explorar a API.
_docs_off = settings.is_production
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=None if _docs_off else f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=None if _docs_off else "/docs",
    redoc_url=None if _docs_off else "/redoc",
    lifespan=lifespan,
)

# M5/M8 (segurança): teto de corpo + nosniff. Adicionado ANTES do CORS para que o CORS fique
# como middleware mais externo (trata o preflight e adiciona os headers ACAO inclusive no 413).
# Teto = maior upload legítimo (MAX_UPLOAD_MB) + margem p/ overhead do multipart/outros campos.
app.add_middleware(
    SecurityMiddleware,
    max_body_bytes=(settings.MAX_UPLOAD_MB + 5) * 1024 * 1024,
)

if settings.CORS_ORIGINS or settings.CORS_ORIGIN_REGEX:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=settings.CORS_ORIGIN_REGEX,  # previews da Vercel, etc.
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.add_exception_handler(LimiteAtivasError, limite_ativas_handler)
app.add_exception_handler(LimiteArmazenamentoError, limite_armazenamento_handler)
app.add_exception_handler(FeatureBloqueadaError, feature_bloqueada_handler)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {"name": settings.PROJECT_NAME, "version": settings.VERSION, "docs": "/docs"}
