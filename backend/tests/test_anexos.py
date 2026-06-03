"""Fase 4 — unidade do que dá p/ testar sem DB: parser da quota, processamento de imagem e o
adapter de storage local (roundtrip + blindagem de path traversal)."""

import asyncio
import io

import pytest
from PIL import Image

from app.core.problems import LimiteArmazenamentoError, limite_armazenamento_from_exc
from app.services.imaging import UnsupportedImage, process_image
from app.services.storage.local import LocalDiskBackend


class _Orig:
    def __init__(self, msg: str):
        self._m = msg

    def __str__(self) -> str:
        return self._m


class _Exc(Exception):
    def __init__(self, msg: str):
        self.orig = _Orig(msg)


# ----------------------------- parser da quota -----------------------------
def test_parse_limite_armazenamento_ok():
    err = limite_armazenamento_from_exc(_Exc("limite_armazenamento:500:524288000"))
    assert isinstance(err, LimiteArmazenamentoError)
    assert err.limite_mb == 500
    assert err.usado_bytes == 524288000


def test_parse_limite_armazenamento_com_contexto_pgsql():
    err = limite_armazenamento_from_exc(
        _Exc("limite_armazenamento:500:1024\nCONTEXT: PL/pgSQL function anexos_quota_guard()")
    )
    assert err.limite_mb == 500
    assert err.usado_bytes == 1024


def test_parse_limite_armazenamento_none_para_outro_erro():
    assert limite_armazenamento_from_exc(_Exc("some other error")) is None


# ----------------------------- processamento de imagem -----------------------------
def _png(w: int, h: int, alpha: bool = False) -> bytes:
    mode, color = ("RGBA", (10, 20, 30, 128)) if alpha else ("RGB", (10, 20, 30))
    buf = io.BytesIO()
    Image.new(mode, (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 100, 50)).save(buf, format="JPEG")
    return buf.getvalue()


def test_process_png_mantem_png_e_thumb_jpeg():
    p = process_image(_png(1200, 800, alpha=True), thumb_px=512, full_max_px=2560)
    assert p.full_content_type == "image/png"
    assert p.full_ext == "png"
    assert (p.largura, p.altura) == (1200, 800)
    assert p.thumb_content_type == "image/jpeg"
    assert len(p.thumb_bytes) > 0
    # a miniatura cabe na caixa de 512
    th = Image.open(io.BytesIO(p.thumb_bytes))
    assert max(th.size) <= 512


def test_process_jpeg_grande_reduz_full():
    p = process_image(_jpeg(3000, 1500), thumb_px=512, full_max_px=2560)
    assert p.full_content_type == "image/jpeg"
    assert (p.largura, p.altura) == (2560, 1280)


def test_process_arquivo_invalido_levanta_unsupported():
    with pytest.raises(UnsupportedImage):
        process_image(b"isto nao e uma imagem", thumb_px=512, full_max_px=2560)


# ----------------------------- storage local -----------------------------
def test_local_storage_roundtrip(tmp_path):
    async def run():
        st = LocalDiskBackend(str(tmp_path))
        key = "t1/o1/a1/full.jpg"
        await st.guardar(key, b"hello-bytes", "image/jpeg")
        assert await st.existe(key) is True
        assert await st.tamanho(key) == len(b"hello-bytes")
        assert await st.recuperar(key) == b"hello-bytes"
        assert key in await st.listar_chaves("t1/o1")
        await st.deletar(key)
        assert await st.existe(key) is False

    asyncio.run(run())


def test_local_storage_deletar_prefixo(tmp_path):
    async def run():
        st = LocalDiskBackend(str(tmp_path))
        await st.guardar("t1/o1/a1/full.jpg", b"x", "image/jpeg")
        await st.guardar("t1/o1/a1/thumb.jpg", b"y", "image/jpeg")
        await st.guardar("t1/o1/a2/full.jpg", b"z", "image/jpeg")
        removidas = await st.deletar_prefixo("t1/o1/a1")
        assert removidas == 2
        assert await st.existe("t1/o1/a1/full.jpg") is False
        assert await st.existe("t1/o1/a2/full.jpg") is True  # a2 intacto

    asyncio.run(run())


def test_local_storage_bloqueia_traversal(tmp_path):
    async def run():
        st = LocalDiskBackend(str(tmp_path))
        with pytest.raises(ValueError):
            await st.guardar("../escapou.jpg", b"x", "image/jpeg")

    asyncio.run(run())
