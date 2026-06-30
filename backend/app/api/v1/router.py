"""Agrega os routers da API v1."""

from fastapi import APIRouter

from app.api.v1.routes import (
    aceites,
    acompanhamento,
    admin,
    anexos,
    assistente,
    auth,
    catalogo,
    checklist,
    cobranca,
    equipes,
    estoque,
    export,
    funcoes,
    health,
    lembretes,
    me,
    membros,
    obras,
    oportunidades,
    portal,
    projeto_vinculo,
    projetos,
    templates,
    vinculo,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(me.router, prefix="/me", tags=["me"])
api_router.include_router(aceites.router, prefix="/me", tags=["aceites"])
api_router.include_router(export.router, prefix="/me", tags=["export"])
api_router.include_router(cobranca.router, prefix="/me", tags=["cobranca"])
api_router.include_router(catalogo.router, prefix="/me/catalogo", tags=["catalogo"])
api_router.include_router(templates.router, prefix="/me/templates", tags=["templates"])
api_router.include_router(equipes.router, prefix="/me/equipes", tags=["equipes"])
api_router.include_router(funcoes.router, prefix="/me/funcoes", tags=["funcoes"])
api_router.include_router(cobranca.webhook_router, prefix="/cobranca", tags=["cobranca"])
api_router.include_router(obras.router, prefix="/obras", tags=["obras"])
api_router.include_router(membros.router, prefix="/obras", tags=["membros"])
api_router.include_router(checklist.router, prefix="/obras", tags=["checklist"])
api_router.include_router(anexos.router, prefix="/obras", tags=["anexos"])
api_router.include_router(estoque.router, prefix="/obras", tags=["estoque"])
api_router.include_router(acompanhamento.router, prefix="/obras", tags=["acompanhamento"])
api_router.include_router(projetos.router, prefix="/projetos", tags=["projetos"])
api_router.include_router(oportunidades.router, prefix="/oportunidades", tags=["oportunidades"])
api_router.include_router(lembretes.router, prefix="/lembretes", tags=["lembretes"])
api_router.include_router(assistente.router, prefix="/assistente", tags=["assistente"])
api_router.include_router(vinculo.router)
api_router.include_router(projeto_vinculo.router)
api_router.include_router(portal.router)
