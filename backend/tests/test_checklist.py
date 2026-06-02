"""Testes da Fase 3 (checklist) sem banco: normalização (chave de dedupe) e parser do template."""

import io

import openpyxl
import pytest
from fastapi import HTTPException

from app.services.checklist_import import TEMPLATE_HEADER, norm_nome, parse_template


def _xlsx(rows: list[tuple]) -> bytes:
    """Monta um .xlsx em memória: 1ª linha = cabeçalho do template, demais = dados."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(TEMPLATE_HEADER))
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------- norm_nome (contrato congelado de dedupe) ----------------
def test_norm_nome_dobra_acento_e_caixa():
    # acento, caixa e espaços: tudo colapsa na MESMA chave (dedupe estável no import/create)
    assert norm_nome("Fundação") == norm_nome("fundacao") == norm_nome("  FUNDACAO ")
    assert norm_nome("Acabamento   Final") == "acabamento final"


def test_norm_nome_forma_unicode():
    composto = "Fundação"  # ç,ã compostos (NFC)
    decomposto = "Fundação"  # c+cedilha, a+til (NFD)
    assert norm_nome(composto) == norm_nome(decomposto)


def test_norm_nome_vazio():
    assert norm_nome("") == ""
    assert norm_nome("   ") == ""


# ---------------- parse_template ----------------
def test_parse_template_arvore_e_forward_fill():
    raw = _xlsx(
        [
            ("Fundação", "Sapatas", 1, 1),
            (None, "Vigas baldrame", None, 2),  # etapa em branco → herda 'Fundação'
            ("Alvenaria", "Blocos", 2, 1),
        ]
    )
    payload = parse_template(raw)
    assert [e["nome"] for e in payload] == ["Fundação", "Alvenaria"]
    fund = payload[0]
    assert fund["nome_norm"] == "fundacao"
    assert [i["nome"] for i in fund["itens"]] == ["Sapatas", "Vigas baldrame"]
    assert payload[1]["itens"][0]["nome"] == "Blocos"


def test_parse_template_dedup_no_arquivo():
    raw = _xlsx(
        [
            ("Pintura", "Massa corrida", 1, 1),
            ("Pintura", "massa  corrida", 1, 2),  # mesma etapa+item normalizados → 1ª vence
        ]
    )
    payload = parse_template(raw)
    assert len(payload) == 1
    assert len(payload[0]["itens"]) == 1


def test_parse_template_cabecalho_invalido_422():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["fase", "tarefa", "x", "y"])  # cabeçalho fora do padrão
    ws.append(["Fundação", "Sapatas", 1, 1])
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(HTTPException) as exc:
        parse_template(buf.getvalue())
    assert exc.value.status_code == 422


def test_parse_template_item_sem_etapa_nao_some_silenciosamente():
    raw = _xlsx([(None, "Item órfão", None, 1)])  # item sem etapa anterior → erro, não drop
    with pytest.raises(HTTPException) as exc:
        parse_template(raw)
    assert exc.value.status_code == 422
    assert "sem etapa" in exc.value.detail


def test_parse_template_nao_e_xlsx_422():
    with pytest.raises(HTTPException) as exc:
        parse_template(b"isto nao e um arquivo xlsx")
    assert exc.value.status_code == 422
