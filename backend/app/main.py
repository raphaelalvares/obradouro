"""Ponto de entrada da API Obra D'Ouro (FastAPI)."""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import assert_safe_db_role, engine
from app.core.middleware import CsrfMiddleware, SecurityMiddleware
from app.core.problems import (
    FeatureBloqueadaError,
    LimiteArmazenamentoError,
    LimiteAtivasError,
    feature_bloqueada_handler,
    limite_armazenamento_handler,
    limite_ativas_handler,
)
from app.core.reaper import reaper_loop

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: garante que a conexão NÃO faz bypass de RLS (a 2ª camada precisa valer)
    await assert_safe_db_role()

    # Reaper do export: re-dispara jobs órfãos (deploy/crash no meio do BackgroundTask). NÃO se dá
    # `await` no 1º sweep aqui — ele roda dentro do próprio loop (create_task); segurar o startup
    # atrasaria o health check se o DB estiver lento. Só sobe fora de teste: o pytest importa a app
    # sem rodar o lifespan, e o gate por ENVIRONMENT é cinto+suspensório caso algum teste use
    # `with TestClient(app)` (senão o reaper bateria no DB fake do conftest).
    reaper_task: asyncio.Task | None = None
    if settings.EXPORT_REAPER_ENABLED and settings.ENVIRONMENT != "test":
        reaper_task = asyncio.create_task(reaper_loop())
        logging.getLogger("cria.export").info(
            "reaper do export ativo (intervalo %ds)", settings.EXPORT_REAPER_INTERVAL_SECONDS
        )
    try:
        yield
    finally:
        # shutdown: encerra o reaper limpo e devolve o pool de conexões
        if reaper_task is not None:
            reaper_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reaper_task
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

# B6 (BFF): CSRF nas requisições autenticadas por cookie. Adicionado DEPOIS do Security (logo, fica
# por fora dele) e ANTES do CORS — assim o CORS, mais externo, ainda trata o preflight e os headers.
app.add_middleware(CsrfMiddleware)

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
