"""Rotas do export de dados do tenant (Fase 8 — portabilidade LGPD). Prefixo /me (ação de conta)."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Response

from app.api.deps import Claims, DbSession
from app.core.http import content_disposition
from app.schemas.export import ExportJobOut
from app.services import export as svc

router = APIRouter()


@router.post("/exports", response_model=ExportJobOut)
async def solicitar(session: DbSession, claims: Claims, background: BackgroundTasks):
    """Pede um export. Cria o job e o processa em background (não segura a resposta — §9)."""
    job = await svc.solicitar(session)
    if job["status"] == "pendente":
        background.add_task(svc.processar, str(job["id"]), claims)
    return job


@router.get("/exports", response_model=list[ExportJobOut])
async def listar(session: DbSession):
    return await svc.listar(session)


@router.get("/exports/{job_id}", response_model=ExportJobOut)
async def get_job(job_id: uuid.UUID, session: DbSession):
    return await svc.get_job(session, job_id)


@router.get("/exports/{job_id}/download")
async def download(job_id: uuid.UUID, session: DbSession):
    data, filename = await svc.baixar(session, job_id)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition(filename, inline=False)},
    )
