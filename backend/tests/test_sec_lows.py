"""Itens de segurança baixos: B8 (Content-Disposition) e B7 (decompression bomb)."""

import io

import pytest
from PIL import Image

from app.core.http import content_disposition
from app.services import imaging


# ---------------------------------------------------------------- B8 (Content-Disposition)
def test_b8_neutraliza_aspas_no_fallback_ascii():
    h = content_disposition('a"b\\c.jpg', inline=True)
    assert h.startswith("inline; ")
    assert 'filename="a_b_c.jpg"' in h  # aspas e barra viram '_' (não quebram a delimitação)


def test_b8_preserva_unicode_via_rfc5987():
    h = content_disposition("piso à vista.jpg", inline=False)
    assert h.startswith("attachment; ")
    assert "filename*=UTF-8''piso%20%C3%A0%20vista.jpg" in h  # 'à' e espaços percent-encoded


def test_b8_nome_vazio_vira_arquivo():
    assert 'filename="arquivo"' in content_disposition("", inline=True)


# ---------------------------------------------------------------- B7 (decompression bomb)
def test_b7_rejeita_bomba_de_descompressao(monkeypatch):
    # imagem real pequena; com o teto rebaixado o decode dispara o bloqueio do Pillow → 415.
    buf = io.BytesIO()
    Image.new("RGB", (60, 60), (1, 2, 3)).save(buf, format="PNG")  # 3600 px
    monkeypatch.setattr(imaging.Image, "MAX_IMAGE_PIXELS", 100)  # 3600 > 2×100 → bomba
    with pytest.raises(imaging.UnsupportedImage):
        imaging.process_image(buf.getvalue(), 32, 64)


def test_b7_imagem_normal_passa():
    buf = io.BytesIO()
    Image.new("RGB", (80, 60), (10, 20, 30)).save(buf, format="PNG")
    out = imaging.process_image(buf.getvalue(), 32, 200)  # full_max_px > lados → sem redução
    assert out.largura == 80 and out.altura == 60
