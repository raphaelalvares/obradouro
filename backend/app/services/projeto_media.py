"""Preparo de upload do Módulo de Projeto (reusa imaging da Fase 4). Revisão aceita PDF; moodboard
só imagem. PDF: valida magic bytes %PDF- (não confia no content_type do multipart), não passa pelo
imaging, sem thumb. Imagem: process_image (thumb + dimensões + reduz)."""

import re

from app.services.imaging import UnsupportedImage, process_image


class UnsupportedUpload(Exception):
    """Arquivo não suportado (→ 415)."""


def sanitize_filename(name: str | None, ext: str) -> str:
    base = (name or "").replace("\\", "/").split("/")[-1]
    base = re.sub(r"[\x00-\x1f]", "", base).strip()
    return (base or f"arquivo.{ext}")[:200]


def prepare_media(raw: bytes, thumb_px: int, full_max_px: int, *, allow_pdf: bool) -> dict:
    """Retorna dict com is_pdf, full_bytes, full_content_type, full_ext, dimensões e thumb_bytes."""
    if allow_pdf and raw[:5] == b"%PDF-":
        return {
            "is_pdf": True,
            "full_bytes": raw,                       # PDF gravado cru (sem re-encode)
            "full_content_type": "application/pdf",  # forçado (ignora o declarado pelo cliente)
            "full_ext": "pdf",
            "largura": None,
            "altura": None,
            "thumb_bytes": None,
        }
    try:
        proc = process_image(raw, thumb_px, full_max_px)
    except UnsupportedImage as e:
        raise UnsupportedUpload("formato não suportado") from e
    return {
        "is_pdf": False,
        "full_bytes": proc.full_bytes,
        "full_content_type": proc.full_content_type,
        "full_ext": proc.full_ext,
        "largura": proc.largura,
        "altura": proc.altura,
        "thumb_bytes": proc.thumb_bytes,
    }
