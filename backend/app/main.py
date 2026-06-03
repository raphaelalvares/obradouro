"""Ponto de entrada da API CRIA (FastAPI)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import assert_safe_db_role, engine
from app.core.problems import LimiteAtivasError, limite_ativas_handler

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: garante que a conexão NÃO faz bypass de RLS (a 2ª camada precisa valer)
    await assert_safe_db_role()
    yield
    # shutdown
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    lifespan=lifespan,
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

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {"name": settings.PROJECT_NAME, "version": settings.VERSION, "docs": "/docs"}
