"""Testes do PDF do checklist (Fase 7) e do processamento do logo — puros, sem DB."""

import io

from PIL import Image

from app.services.imaging import process_logo
from app.services.pdf_render import _agrupar, _lat1, _num, render_checklist_pdf


def _arvore() -> list[dict]:
    return [
        {
            "nome": "Alvenaria",
            "seq_humano": 1,
            # 4 níveis: subetapa com tarefas + subetapa-marco (sem tarefas) + tarefas diretas.
            "subetapas": [
                {
                    "nome": "Fundação",
                    "seq_humano": 5,
                    "concluida": False,
                    "itens": [
                        {"nome": "Sapata", "estado": "concluido", "ambiente": "Garagem",
                         "subitens": []},
                    ],
                },
                {"nome": "Marco vazio", "seq_humano": 6, "concluida": True, "itens": []},
            ],
            "itens": [
                {
                    "nome": "Parede da sala",
                    "estado": "pendente",
                    "ambiente": "Sala",
                    "quantidade": 12.5,
                    "unidade": "m2",
                    "subitens": [
                        {"nome": "Marcar", "estado": "concluido", "concluido_por_nome": "João"},
                        {"nome": "Levantar", "estado": "pendente"},
                    ],
                },
                {"nome": "Item solto", "estado": "em_andamento", "ambiente": None, "subitens": []},
            ],
        }
    ]


def _png(w: int, h: int, mode: str = "RGBA") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, (w, h), (216, 165, 58, 255) if mode == "RGBA" else (216, 165, 58)).save(
        buf, "PNG"
    )
    return buf.getvalue()


def test_render_produz_pdf():
    out = render_checklist_pdf(
        {"nome": "Reforma Apto 302", "seq_humano": 42},
        _arvore(),
        "Escritório Acme",
        None,
        "01/01/2026 10:00",
    )
    assert out[:5] == b"%PDF-"
    assert len(out) > 800


def test_render_checklist_vazio():
    out = render_checklist_pdf({"nome": "X", "seq_humano": 1}, [], None, None, "01/01/2026 10:00")
    assert out[:5] == b"%PDF-"


def test_render_etapa_marco():
    # etapa-marco (sem subetapas e sem tarefas): renderiza só o estado de conclusão.
    arvore = [{"nome": "Vistoria final", "seq_humano": 9, "sem_itens": True, "concluida": True}]
    out = render_checklist_pdf({"nome": "Obra", "seq_humano": 1}, arvore, None, None, "01/01 10:00")
    assert out[:5] == b"%PDF-"


def test_render_com_logo():
    out = render_checklist_pdf(
        {"nome": "Obra", "seq_humano": 1}, _arvore(), "Acme", _png(120, 40), "01/01/2026 10:00"
    )
    assert out[:5] == b"%PDF-"


def test_render_logo_invalido_nao_quebra():
    # bytes que não são imagem: o logo é decorativo → PDF sai mesmo assim.
    out = render_checklist_pdf(
        {"nome": "Obra", "seq_humano": 1}, _arvore(), None, b"isto nao e imagem", "01/01 10:00"
    )
    assert out[:5] == b"%PDF-"


def test_lat1_normaliza_unicode():
    assert _lat1("a—b") == "a-b"
    assert _lat1("“aspas”") == '"aspas"'
    assert _lat1("ção") == "ção"  # português está no latin-1
    assert _lat1(None) == ""


def test_num_formato_br():
    assert _num(10) == "10"
    assert _num(10.0) == "10"
    assert _num(12.5) == "12,5"
    assert _num("x") == "x"


def test_agrupar_preserva_ordem_e_separa_sem_ambiente():
    itens = [
        {"nome": "a", "ambiente": "Cozinha"},
        {"nome": "b", "ambiente": None},
        {"nome": "c", "ambiente": "Cozinha"},
    ]
    grupos = _agrupar(itens)
    assert [amb for amb, _ in grupos] == ["Cozinha", None]
    assert [it["nome"] for it in grupos[0][1]] == ["a", "c"]


def test_process_logo_converte_para_png_e_reduz():
    buf = io.BytesIO()
    Image.new("RGB", (1000, 400), (10, 20, 30)).save(buf, "JPEG")
    out = process_logo(buf.getvalue(), max_px=300)
    img = Image.open(io.BytesIO(out))
    assert img.format == "PNG"
    assert max(img.size) <= 300
