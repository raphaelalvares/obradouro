"""Agrega os routers da API v1."""

from fastapi import APIRouter

from app.api.v1.routes import (
    aceites,
    anexos,
    checklist,
    cobranca,
    estoque,
    export,
    health,
    me,
    membros,
    obras,
    projeto_vinculo,
    projetos,
    vinculo,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(me.router, prefix="/me", tags=["me"])
api_router.include_router(aceites.router, prefix="/me", tags=["aceites"])
api_router.include_router(export.router, prefix="/me", tags=["export"])
api_router.include_router(cobranca.router, prefix="/me", tags=["cobranca"])
api_router.include_router(cobranca.webhook_router, prefix="/cobranca", tags=["cobranca"])
api_router.include_router(obras.router, prefix="/obras", tags=["obras"])
api_router.include_router(membros.router, prefix="/obras", tags=["membros"])
api_router.include_router(checklist.router, prefix="/obras", tags=["checklist"])
api_router.include_router(anexos.router, prefix="/obras", tags=["anexos"])
api_router.include_router(estoque.router, prefix="/obras", tags=["estoque"])
api_router.include_router(projetos.router, prefix="/projetos", tags=["projetos"])
api_router.include_router(vinculo.router)
api_router.include_router(projeto_vinculo.router)
