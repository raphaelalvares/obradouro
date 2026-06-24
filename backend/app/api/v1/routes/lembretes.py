"""Rota dos LEMBRETES comerciais (apontamentos do agente). Read-only, tenant-scoped via RLS."""

from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.lembretes import ApontamentoOut
from app.services import lembretes as svc

router = APIRouter()


@router.get("", response_model=list[ApontamentoOut])
async def listar_lembretes(session: DbSession):
    """Apontamentos do funil (follow-ups, esfriando, proposta parada…). RLS escopa ao dono."""
    return await svc.listar_apontamentos(session)
