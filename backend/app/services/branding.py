"""Serviço da marca do escritório (Fase 7 — personalização: nome + logo).

Marca é nível-CONTA (por tenant = o arquiteto), não por obra. O byte do logo trafega como qualquer
mídia (API-only) e vive no storage (módulo da Fase 4); a tabela só guarda a chave + mime. As
MUTAÇÕES (definir nome / subir logo) ficam atrás da flag de plano 'logo' → FeatureBloqueadaError
(403 + upsell). Ler e remover são livres (limpeza pós-downgrade não pode ficar presa).
"""

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import run_cpu
from app.core.config import get_settings
from app.core.problems import FeatureBloqueadaError
from app.schemas.branding import BrandingUpdate
from app.services import planos as planos_svc
from app.services.imaging import UnsupportedImage, process_logo
from app.services.storage import get_storage

settings = get_settings()

_DETALHE_LOGO = "A personalização (logo do escritório) está disponível no plano Pro."


async def _assert_pode_personalizar(session: AsyncSession) -> None:
    if not await planos_svc.tem_flag(session, "logo"):
        raise FeatureBloqueadaError("logo", _DETALHE_LOGO)


async def get_branding(session: AsyncSession) -> dict:
    """Marca do usuário corrente (RLS escopa à própria linha) + se o plano permite personalizar."""
    row = (
        await session.execute(
            text(
                "select nome_escritorio, logo_key, logo_mime from public.tenant_branding "
                "where tenant_id = (select auth.uid())"
            )
        )
    ).first()
    return {
        "nome_escritorio": row.nome_escritorio if row else None,
        "tem_logo": bool(row and row.logo_key),
        "logo_mime": row.logo_mime if row else None,
        "pode_personalizar": await planos_svc.tem_flag(session, "logo"),
    }


async def update_branding(session: AsyncSession, user_id: str, data: BrandingUpdate) -> dict:
    """Define o nome do escritório (upsert). Gated pela flag 'logo'."""
    await _assert_pode_personalizar(session)
    nome = (data.nome_escritorio or "").strip() or None
    # tabela sem trigger de seq → ON CONFLICT é seguro aqui (não queima sequencial).
    await session.execute(
        text(
            """
            insert into public.tenant_branding (tenant_id, nome_escritorio)
            values ((select auth.uid()), :n)
            on conflict (tenant_id) do update set nome_escritorio = excluded.nome_escritorio
            """
        ),
        {"n": nome},
    )
    return await get_branding(session)


async def upload_logo(session: AsyncSession, user_id: str, arquivo) -> dict:
    """Sobe/substitui o logo do escritório. Gated pela flag 'logo'. Normaliza p/ PNG."""
    await _assert_pode_personalizar(session)
    raw = await arquivo.read()
    if not raw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "arquivo vazio")
    if len(raw) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"arquivo acima do limite de {settings.MAX_UPLOAD_MB} MB",
        )
    try:
        png = await run_cpu(process_logo, raw)
    except UnsupportedImage as e:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "formato de imagem não suportado"
        ) from e

    key = f"branding/{user_id}/logo.png"
    await get_storage().guardar(key, png, "image/png")
    await session.execute(
        text(
            """
            insert into public.tenant_branding (tenant_id, logo_key, logo_mime)
            values ((select auth.uid()), :k, 'image/png')
            on conflict (tenant_id) do update set
              logo_key = excluded.logo_key, logo_mime = excluded.logo_mime
            """
        ),
        {"k": key},
    )
    return await get_branding(session)


async def serve_logo(session: AsyncSession) -> tuple[bytes, str]:
    """Bytes + content_type do logo do usuário corrente (preview na conta). 404 se não houver."""
    row = (
        await session.execute(
            text(
                "select logo_key, logo_mime from public.tenant_branding "
                "where tenant_id = (select auth.uid())"
            )
        )
    ).first()
    if row is None or not row.logo_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "sem logo")
    try:
        data = await get_storage().recuperar(row.logo_key)
    except FileNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conteúdo do logo não encontrado") from e
    return data, row.logo_mime or "image/png"


async def delete_logo(session: AsyncSession, user_id: str) -> dict:
    """Remove o logo (livre — permite limpar mesmo após downgrade). Best-effort no storage."""
    row = (
        await session.execute(
            text(
                "select logo_key from public.tenant_branding "
                "where tenant_id = (select auth.uid())"
            )
        )
    ).first()
    if row and row.logo_key:
        await get_storage().deletar(row.logo_key)
    await session.execute(
        text(
            "update public.tenant_branding set logo_key = null, logo_mime = null "
            "where tenant_id = (select auth.uid())"
        )
    )
    return await get_branding(session)
