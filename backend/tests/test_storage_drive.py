"""Unidade do adapter de Google Drive: as partes PURAS (sem rede/credencial) — split de chave,
escaping do parâmetro q, corpo multipart e blindagem de path traversal. As chamadas ao Drive em si
são IO (fora do escopo do pytest, que roda sem credencial)."""

import pytest

from app.services.storage.drive import (
    _multipart_body,
    _q_escape,
    _segments,
    _split_key,
)


def test_split_key_pastas_e_arquivo():
    assert _split_key("t1/o1/a1/full.jpg") == (["t1", "o1", "a1"], "full.jpg")
    assert _split_key("branding/uid/logo.png") == (["branding", "uid"], "logo.png")
    # arquivo na raiz (sem pastas)
    assert _split_key("export.zip") == ([], "export.zip")


def test_segments_normaliza_barras():
    assert _segments("t1/o1") == ["t1", "o1"]
    assert _segments("/t1//o1/") == ["t1", "o1"]
    assert _segments("t1\\o1") == ["t1", "o1"]  # barra invertida do Windows


def test_split_key_bloqueia_traversal():
    with pytest.raises(ValueError):
        _split_key("../escapou.jpg")
    with pytest.raises(ValueError):
        _split_key("t1/../../etc/passwd")
    with pytest.raises(ValueError):
        _split_key("")  # chave vazia


def test_q_escape():
    assert _q_escape("full.jpg") == "full.jpg"
    assert _q_escape("a'b") == "a\\'b"
    assert _q_escape("a\\b") == "a\\\\b"


def test_multipart_body_bem_formado():
    body = _multipart_body(
        {"name": "full.jpg", "parents": ["ROOT"]}, b"\x00\x01BYTES", "image/jpeg", "BND"
    )
    assert body.startswith(b"--BND\r\n")
    assert body.endswith(b"--BND--")
    assert b'"name": "full.jpg"' in body
    assert b"Content-Type: image/jpeg" in body
    assert b"\x00\x01BYTES" in body  # a mídia crua (binária) entra intacta
