"""Fase 5 — unidade do que dá p/ testar sem DB: preparo de mídia (PDF vs imagem) e a regra
'além do incluído' (numero > revisoes_incluidas)."""

import io

import pytest
from PIL import Image
from pydantic import ValidationError

from app.schemas.revisoes import RevisaoDecisao
from app.services.projeto_media import UnsupportedUpload, prepare_media, sanitize_filename
from app.services.revisoes import _alem


def _png(w=400, h=300) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (30, 40, 50)).save(buf, format="PNG")
    return buf.getvalue()


# ----------------------------- prepare_media -----------------------------
def test_prepare_media_pdf():
    raw = b"%PDF-1.7\n...conteudo arbitrario..."
    m = prepare_media(raw, 512, 2560, allow_pdf=True)
    assert m["is_pdf"] is True
    assert m["full_content_type"] == "application/pdf"
    assert m["full_ext"] == "pdf"
    assert m["thumb_bytes"] is None
    assert m["full_bytes"] == raw  # PDF gravado cru


def test_prepare_media_imagem():
    m = prepare_media(_png(), 512, 2560, allow_pdf=True)
    assert m["is_pdf"] is False
    assert m["full_content_type"] == "image/png"
    assert m["thumb_bytes"] and len(m["thumb_bytes"]) > 0
    assert (m["largura"], m["altura"]) == (400, 300)


def test_prepare_media_pdf_barrado_quando_nao_permitido():
    # moodboard (allow_pdf=False): bytes de PDF não são imagem → UnsupportedUpload
    with pytest.raises(UnsupportedUpload):
        prepare_media(b"%PDF-1.7\nxxx", 512, 2560, allow_pdf=False)


def test_prepare_media_lixo_levanta():
    with pytest.raises(UnsupportedUpload):
        prepare_media(b"isto nao e imagem nem pdf", 512, 2560, allow_pdf=True)


def test_sanitize_filename():
    assert sanitize_filename("../../etc/passwd", "jpg") == "passwd"
    assert sanitize_filename(None, "pdf") == "arquivo.pdf"
    assert sanitize_filename("foto bonita.png", "png") == "foto bonita.png"


# ----------------------------- além do incluído -----------------------------
def test_alem_do_incluido():
    # incluidas=3 (alterações): R0..R3 incluídas; R4+ além. R0 = entrega base.
    assert _alem(0, 3) is False
    assert _alem(3, 3) is False
    assert _alem(4, 3) is True
    # None = arquiteto não controla → nunca sinaliza
    assert _alem(99, None) is False
    # incluidas=0: qualquer alteração (R1+) já é além; R0 não
    assert _alem(0, 0) is False
    assert _alem(1, 0) is True


# ----------------------------- RevisaoDecisao (layouts 1-de-N, 0098) -----------------------------
def test_decisao_escolher_exige_opcao():
    d = RevisaoDecisao(acao="escolher", opcao_escolhida=2)
    assert d.acao == "escolher" and d.opcao_escolhida == 2
    with pytest.raises(ValidationError):  # escolher sem opção
        RevisaoDecisao(acao="escolher")


def test_decisao_opcao_so_em_escolher():
    # aprovar/alteracao/recusar não aceitam opcao_escolhida
    with pytest.raises(ValidationError):
        RevisaoDecisao(acao="aprovar", opcao_escolhida=1)
    with pytest.raises(ValidationError):
        RevisaoDecisao(acao="recusar", motivo="x", opcao_escolhida=1)
    # sem opção seguem válidas
    assert RevisaoDecisao(acao="aprovar").opcao_escolhida is None


def test_decisao_opcao_faixa_1_a_9():
    assert RevisaoDecisao(acao="escolher", opcao_escolhida=9).opcao_escolhida == 9
    with pytest.raises(ValidationError):
        RevisaoDecisao(acao="escolher", opcao_escolhida=0)
    with pytest.raises(ValidationError):
        RevisaoDecisao(acao="escolher", opcao_escolhida=10)
