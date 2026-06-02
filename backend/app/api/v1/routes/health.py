"""Endpoints de health check (sem autenticação)."""

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.database import check_db_connection

router = APIRouter()
settings = get_settings()


@router.get("")
async def health() -> dict:
    """Liveness: a aplicação está de pé (não toca no banco)."""
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "version": settings.VERSION,
    }


@router.get("/db")
async def health_db() -> dict:
    """Readiness: o banco está acessível (ping simples, sem contexto de RLS)."""
    await check_db_connection()
    return {"status": "ok", "database": "reachable"}
