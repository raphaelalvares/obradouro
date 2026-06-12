"""Testes do PDF da proposta comercial — puros, sem DB (espelham test_pdf.py)."""

import io

from PIL import Image

from app.services.orcamento_pdf_render import _brl, _data_br, render_orcamento_pdf


def _proposta() -> dict:
    import datetime as dt

    return {
        "projeto_nome": "Reforma Apto 302",
        "numero": 1,
        "data": dt.date(2026, 6, 1),
        "validade": dt.date(2026, 7, 1),
        "observacoes": "50% na assinatura — 50% na entrega.",
        "preco_final": 14058.0,
        "etapas": [
            {
                "etapa": "Pintura",
                "valor": 250.0,
                "itens": [
                    {"descricao": "Parede da sala", "ambiente": "Sala", "unidade": "m²",
                     "quantidade": 12.5, "valor": 150.0},
                    {"descricao": "Teto", "ambiente": None, "unidade": None,
                     "quantidade": None, "valor": 100.0},
                ],
            }
        ],
    }


def _png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (w, h), (216, 165, 58, 255)).save(buf, "PNG")
    return buf.getvalue()


def test_render_produz_pdf():
    out = render_orcamento_pdf(_proposta(), "Escritório Acme", None, "01/06/2026 10:00")
    assert out[:5] == b"%PDF-"
    assert len(out) > 800


def test_render_sem_itens_e_sem_marca():
    p = _proposta()
    p["etapas"] = []
    p["observacoes"] = None
    out = render_orcamento_pdf(p, None, None, "01/06/2026 10:00")
    assert out[:5] == b"%PDF-"


def test_render_com_logo():
    out = render_orcamento_pdf(_proposta(), "Acme", _png(120, 40), "01/06/2026 10:00")
    assert out[:5] == b"%PDF-"


def test_render_logo_invalido_nao_quebra():
    out = render_orcamento_pdf(_proposta(), "Acme", b"isto nao e imagem", "01/06/2026 10:00")
    assert out[:5] == b"%PDF-"


def test_render_proposta_longa_pagina():
    # mais linhas do que cabe numa página A4 → quebra sem rasgar texto/valor.
    p = _proposta()
    p["etapas"] = [
        {
            "etapa": f"Etapa {n}",
            "valor": 100.0,
            "itens": [
                {"descricao": "Serviço com uma descrição razoavelmente longa para forçar "
                              "múltiplas linhas no PDF", "ambiente": "Sala", "unidade": "m²",
                 "quantidade": 3, "valor": 50.0}
                for _ in range(6)
            ],
        }
        for n in range(12)
    ]
    out = render_orcamento_pdf(p, "Acme", None, "01/06/2026 10:00")
    assert out[:5] == b"%PDF-"


def test_brl_formato_br():
    assert _brl(14058) == "R$ 14.058,00"
    assert _brl(1234.5) == "R$ 1.234,50"
    assert _brl(None) == "R$ 0,00"


def test_data_br():
    import datetime as dt

    assert _data_br(dt.date(2026, 7, 1)) == "01/07/2026"
    assert _data_br(None) == "-"
