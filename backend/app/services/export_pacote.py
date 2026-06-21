"""Montagem do pacote de export (Fase 8) — funções PURAS (sem DB/storage): viram CSV legível e o
.zip "em camadas". Testáveis isoladamente (ver tests/test_export.py); o service só alimenta dados.

Camadas do .zip (planejamento §9): fotos organizadas por obra + export legível (CSV de checklist e
estoque por obra). Dump bruto de SQL fica para depois (foto + CSV já cobre a portabilidade útil).

CSV: separador ';' e BOM utf-8 — abre direto no Excel pt-BR (vírgula decimal, acento correto).
"""

import csv
import io
import re
import unicodedata
import zipfile


def slug(s: str | None, fallback: str = "obra") -> str:
    """Nome de pasta seguro: minúsculo, ascii, só [a-z0-9-]."""
    base = unicodedata.normalize("NFKD", (s or "").strip())
    base = base.encode("ascii", "ignore").decode("ascii").lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base or fallback


def _num(n) -> str:
    """Número no formato BR (vírgula decimal); inteiro sem casas; vazio se None."""
    if n is None or n == "":
        return ""
    try:
        f = float(n)
    except (TypeError, ValueError):
        return str(n)
    if f == int(f):
        return str(int(f))
    return f"{f:.3f}".rstrip("0").rstrip(".").replace(".", ",")


def _txt(v) -> str:
    if v is None:
        return ""
    if hasattr(v, "strftime"):  # date/datetime
        return v.strftime("%d/%m/%Y %H:%M") if hasattr(v, "hour") else v.strftime("%d/%m/%Y")
    return str(v)


_CHECKLIST_COLS = [
    ("etapa_seq", "Etapa #"),
    ("etapa", "Etapa"),
    ("subetapa", "Subetapa"),
    ("nivel", "Nível"),
    ("item", "Item"),
    ("estado", "Estado"),
    ("ambiente", "Cômodo"),
    ("unidade", "Unid."),
    ("quantidade", "Qtd"),
    ("custo_total", "Custo (R$)"),
    ("concluido_por", "Concluído por"),
    ("concluido_em", "Concluído em"),
]

_ESTOQUE_COLS = [
    ("nf", "NF-e"),
    ("fornecedor", "Fornecedor"),
    ("data_chegada", "Chegada"),
    ("item", "Item"),
    ("unidade", "Unid."),
    ("quantidade_nota", "Qtd nota"),
    ("quantidade_conferida", "Qtd contada"),
    ("valor_unitario", "Valor unit. (R$)"),
    ("valor_total", "Valor total (R$)"),
]

_NUM_KEYS = {"quantidade", "custo_total", "quantidade_nota", "quantidade_conferida",
             "valor_unitario", "valor_total"}


def _csv(cols: list[tuple[str, str]], linhas: list[dict]) -> str:
    out = io.StringIO()
    w = csv.writer(out, delimiter=";", lineterminator="\n")
    w.writerow([titulo for _, titulo in cols])
    for r in linhas:
        w.writerow([
            _num(r.get(k)) if k in _NUM_KEYS else _txt(r.get(k)) for k, _ in cols
        ])
    return out.getvalue()


def csv_checklist(linhas: list[dict]) -> str:
    return _csv(_CHECKLIST_COLS, linhas)


def csv_estoque(linhas: list[dict]) -> str:
    return _csv(_ESTOQUE_COLS, linhas)


def _bom(s: str) -> bytes:
    return ("﻿" + s).encode("utf-8")  # BOM → Excel reconhece utf-8


def _leia_me(obras: list[dict], gerado_em: str) -> str:
    linhas = [
        "Pacote de dados — CRIA (gestão de obra)",
        f"Gerado em: {gerado_em}",
        "",
        "Este pacote contém seus dados em camadas:",
        "  - uma pasta por obra;",
        "  - checklist.csv  = etapas, subetapas, tarefas e itens (estado, cômodo, orçamento);",
        "  - estoque.csv    = itens das notas fiscais importadas (nota x contagem);",
        "  - fotos/         = as fotos anexadas à obra.",
        "",
        "Os CSV usam ';' como separador e abrem direto no Excel/Google Sheets.",
        "",
        f"Obras neste pacote ({len(obras)}):",
    ]
    linhas += [f"  - {o['pasta']}" for o in obras]
    return "\n".join(linhas) + "\n"


def montar_zip(obras: list[dict], fotos: list[tuple[str, bytes]], gerado_em: str) -> bytes:
    """Monta o .zip. `obras` = [{pasta, checklist_csv, estoque_csv}]; `fotos` = [(caminho_no_zip,
    bytes)] (o caminho já inclui a pasta da obra)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("leia-me.txt", _bom(_leia_me(obras, gerado_em)))
        for o in obras:
            z.writestr(f"{o['pasta']}/checklist.csv", _bom(o["checklist_csv"]))
            z.writestr(f"{o['pasta']}/estoque.csv", _bom(o["estoque_csv"]))
        for caminho, data in fotos:
            z.writestr(caminho, data)
    return buf.getvalue()
