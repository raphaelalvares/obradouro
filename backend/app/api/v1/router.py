"""Agrega os routers da API v1."""

from fastapi import APIRouter

from app.api.v1.routes import anexos, checklist, health, me, membros, obras, vinculo

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(me.router, prefix="/me", tags=["me"])
api_router.include_router(obras.router, prefix="/obras", tags=["obras"])
api_router.include_router(membros.router, prefix="/obras", tags=["membros"])
api_router.include_router(checklist.router, prefix="/obras", tags=["checklist"])
api_router.include_router(anexos.router, prefix="/obras", tags=["anexos"])
api_router.include_router(vinculo.router)
