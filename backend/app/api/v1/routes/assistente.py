"""Rota do assistente conversacional (chat). Read-only, tenant-scoped via RLS."""

from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.assistente import AssistenteIn, AssistenteOut
from app.services import assistente as svc

router = APIRouter()


@router.post("", response_model=AssistenteOut)
async def conversar(data: AssistenteIn, session: DbSession):
    """Pergunta do usuário → resposta sobre os dados dele (comercial). Precisa do Ollama ligado."""
    return await svc.responder(session, data)
