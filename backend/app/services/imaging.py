"""Processamento de imagem do anexo (Pillow): orienta pela EXIF, mede, reduz o 'full' acima do
limite (poupa storage/quota) e gera a miniatura. HEIC/HEIF do iPhone é convertido p/ JPEG (os
browsers não exibem HEIC) — registramos o opener se o wheel pillow-heif estiver disponível, senão
HEIC degrada para 415 (resto dos formatos segue normal).

Tudo em memória (uploads são limitados por MAX_UPLOAD_MB antes de chegar aqui).
"""

import io
from dataclasses import dataclass

from PIL import Image, ImageOps

try:  # pillow-heif é opcional; sem ele, HEIC vira "formato não suportado" (415) sem quebrar o resto
    import pillow_heif

    pillow_heif.register_heif_opener()
except Exception:  # noqa: BLE001  (qualquer falha de import/registro = sem suporte HEIC)
    pass

# Formatos mantidos como 'full' tal qual (browsers exibem). Os demais (HEIC, BMP, TIFF…) viram JPEG.
_KEEP = {"JPEG", "PNG", "WEBP"}


class UnsupportedImage(Exception):
    """Bytes recebidos não são uma imagem que sabemos processar (→ 415 na rota)."""


@dataclass
class ProcessedImage:
    full_bytes: bytes
    full_content_type: str
    full_ext: str
    largura: int
    altura: int
    thumb_bytes: bytes
    thumb_content_type: str  # sempre image/jpeg


def _flatten(img: Image.Image) -> Image.Image:
    """Achata transparência sobre branco e devolve RGB (p/ salvar em JPEG)."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        return bg
    return img.convert("RGB")


def process_image(raw: bytes, thumb_px: int, full_max_px: int) -> ProcessedImage:
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as e:  # noqa: BLE001
        raise UnsupportedImage("arquivo não é uma imagem suportada") from e

    src_format = (img.format or "").upper()    # capturar ANTES do transpose (que perde .format)
    img = ImageOps.exif_transpose(img) or img  # respeita a orientação da câmera
    out_format = src_format if src_format in _KEEP else "JPEG"

    if max(img.size) > full_max_px:                  # só reduz (thumbnail nunca amplia)
        img.thumbnail((full_max_px, full_max_px))
    largura, altura = img.size

    full = io.BytesIO()
    if out_format == "JPEG":
        _flatten(img).save(full, format="JPEG", quality=85, optimize=True, progressive=True)
        full_ct, full_ext = "image/jpeg", "jpg"
    elif out_format == "PNG":
        img.save(full, format="PNG", optimize=True)
        full_ct, full_ext = "image/png", "png"
    else:  # WEBP
        img.save(full, format="WEBP", quality=85, method=4)
        full_ct, full_ext = "image/webp", "webp"

    thumb_img = img.copy()
    thumb_img.thumbnail((thumb_px, thumb_px))
    thumb = io.BytesIO()
    _flatten(thumb_img).save(thumb, format="JPEG", quality=80, optimize=True)

    return ProcessedImage(
        full_bytes=full.getvalue(),
        full_content_type=full_ct,
        full_ext=full_ext,
        largura=largura,
        altura=altura,
        thumb_bytes=thumb.getvalue(),
        thumb_content_type="image/jpeg",
    )
