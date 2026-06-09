"""Parser de .xlsx do import + normalizacao de nome (chave de dedupe).

Dois formatos aceitos, AUTO-DETECTADOS por `parse_xlsx`:
  (A) Template do app  — cabecalho na 1a linha: etapa, item, ordem_etapa, ordem_item.
  (B) Planilha de ORCAMENTO real do usuario — cabecalho "ITEM | DESCRICAO DOS SERVICOS | UNIDADE |
      QUANTIDADE | M.O | MAT | TOTAL" em alguma linha; etapa = codigo de 2 digitos (01..20),
      servico = codigo XX.YY (vira tarefa com unidade/quantidade/M.O/material/total).

`norm_nome` e o CONTRATO CONGELADO da chave natural: gravado em etapas/checklist_itens.nome_norm
tanto no create manual quanto no import; os unique indexes (obra,nome_norm)/(etapa,nome_norm) fazem
o dedupe. Dobra acento e forma Unicode (NFKD + remove diacriticos + casefold + colapsa espacos).
"""

import io
import re
import unicodedata

from fastapi import HTTPException, status

MAX_XLSX_BYTES = 2 * 1024 * 1024  # guarda anti zip-bomb / arquivo gigante
MAX_LINHAS = 5000
# colunas FIXAS do template do app (poka-yoke: "nao e qualquer Excel").
TEMPLATE_HEADER = ("etapa", "item", "ordem_etapa", "ordem_item")

# orcamento: etapa = "01".."20"; servico = "XX.YY". Casados no codigo da coluna ITEM.
_RE_ETAPA = re.compile(r"^\d{1,2}$")
_RE_ITEM = re.compile(r"^\d{1,2}\.\d{1,2}$")


def norm_nome(s: str) -> str:
    """Chave de dedupe (contrato congelado). NFKD -> sem diacritico -> casefold -> 1 espaco."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))  # remove acentos/diacriticos
    return re.sub(r"\s+", " ", s).strip().casefold()


def _num(v: object) -> float | None:
    """Le valor monetario/quantidade do orcamento. Aceita numero, BR ('R$9.000,00'), ponto-decimal;
    'X'/'-'/vazio -> None (sem custo aplicavel). Falha de parse -> None (nao explode o import)."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower().replace("r$", "").replace(" ", "")
    if s in ("", "x", "-", "–", "—"):
        return None
    if "." in s and "," in s:        # 9.000,00 -> 9000.00 (ponto=milhar, virgula=decimal)
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                   # 1234,5 -> 1234.5
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _as_int(v: object) -> int:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _load_rows(raw: bytes) -> list[tuple]:
    """Le o .xlsx (size guard) e devolve as linhas da aba ativa como tuplas (cap MAX_LINHAS)."""
    if len(raw) > MAX_XLSX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "arquivo grande demais")
    try:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "arquivo nao e um .xlsx valido"
        ) from e
    rows: list[tuple] = []
    for i, r in enumerate(wb.active.iter_rows(values_only=True)):
        if i >= MAX_LINHAS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "planilha excede o limite de linhas"
            )
        rows.append(r)
    return rows


def _cell(r: tuple, i: int) -> str:
    v = r[i] if len(r) > i else None
    return str(v).strip() if v is not None else ""


def _detect(rows: list[tuple]) -> tuple[str | None, int]:
    """Detecta o formato. Retorna ('template'|'orcamento'|None, indice_do_cabecalho)."""
    if rows:
        h0 = tuple(
            (str(c).strip().lower() if c is not None else "") for c in (rows[0][:4])
        )
        if h0 == TEMPLATE_HEADER:
            return ("template", 0)
    # orcamento: procura uma linha com A='item' e B contendo 'descri' (DESCRICAO DOS SERVICOS)
    for i, r in enumerate(rows[:25]):
        if _cell(r, 0).lower() == "item" and "descri" in _cell(r, 1).lower():
            return ("orcamento", i)
    return (None, -1)


def parse_xlsx(raw: bytes) -> list[dict]:
    """Detecta o formato e devolve a arvore [{nome,nome_norm,ordem,itens:[...]}] p/ o RPC."""
    rows = _load_rows(raw)
    kind, idx = _detect(rows)
    if kind == "template":
        return _parse_template_rows(rows)
    if kind == "orcamento":
        return _parse_orcamento_rows(rows, idx)
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "xlsx fora dos formatos suportados (template do app ou planilha de orcamento)",
    )


def parse_template(raw: bytes) -> list[dict]:
    """Compat/uso direto: exige o template do app (cabecalho na 1a linha)."""
    return _parse_template_rows(_load_rows(raw))


def _parse_template_rows(rows: list[tuple]) -> list[dict]:
    """Template do app: 1a linha = cabecalho fixo; etapa em A, item em B (forward-fill da etapa).

    Nao descarta linha em silencio: item sem etapa vira erro com o numero da linha. Dedupe DENTRO
    do arquivo: 1a ocorrencia de cada (etapa)/(etapa,item) vence.
    """
    header = tuple(
        (str(c).strip().lower() if c is not None else "")
        for c in (rows[0][: len(TEMPLATE_HEADER)] if rows else ())
    )
    if header[: len(TEMPLATE_HEADER)] != TEMPLATE_HEADER:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "template fora do padrao (cabecalho esperado: etapa, item, ordem_etapa, ordem_item)",
        )

    etapas: dict[str, dict] = {}
    last_etapa: str | None = None
    erros: list[str] = []

    for linha, r in enumerate(rows[1:], start=2):
        etapa_raw = r[0] if len(r) > 0 else None
        item_raw = r[1] if len(r) > 1 else None
        oe = r[2] if len(r) > 2 else None
        oi = r[3] if len(r) > 3 else None

        if etapa_raw is not None and str(etapa_raw).strip():
            nome = str(etapa_raw).strip()
            en = norm_nome(nome)
            last_etapa = en
            etapas.setdefault(
                en, {"nome": nome, "nome_norm": en, "ordem": _as_int(oe), "itens": {}}
            )

        if item_raw is not None and str(item_raw).strip():
            if last_etapa is None:
                erros.append(f"linha {linha}: item sem etapa")
                continue
            iname = str(item_raw).strip()
            inorm = norm_nome(iname)
            if inorm:
                etapas[last_etapa]["itens"].setdefault(
                    inorm, {"nome": iname, "nome_norm": inorm, "ordem": _as_int(oi)}
                )

    if erros:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "; ".join(erros[:20]))

    return [
        {
            "nome": e["nome"],
            "nome_norm": e["nome_norm"],
            "ordem": e["ordem"],
            "itens": list(e["itens"].values()),
        }
        for e in etapas.values()
    ]


def _at(r: tuple, idx: int | None):
    """Celula crua na coluna idx (None-safe)."""
    return r[idx] if (idx is not None and len(r) > idx) else None


def _orcamento_cols(header: tuple) -> dict:
    """Mapeia as colunas do orcamento pelo CABECALHO (nomes), com fallback p/ posicoes fixas.

    Padrao classico: A=ITEM, B=DESCRICAO, C=UNIDADE, D=QUANTIDADE, E=M.O, F=MAT, G=TOTAL. A coluna
    EQUIP/EQUIPAMENTO e OPCIONAL (pode estar em qualquer posicao; ausente => None => custo 0/None).
    """
    idx = {"item": 0, "descricao": 1, "unidade": 2, "quantidade": 3, "mo": 4,
           "material": 5, "total": 6, "equipamento": None}
    found: dict = {}
    for i, c in enumerate(header):
        h = (str(c).strip().lower() if c is not None else "")
        if not h:
            continue
        if "equip" in h:
            found.setdefault("equipamento", i)
        elif h.startswith("item"):
            found.setdefault("item", i)
        elif "descri" in h:
            found.setdefault("descricao", i)
        elif h.startswith("unid") or h == "un":
            found.setdefault("unidade", i)
        elif h.startswith("quant") or h == "qtd":
            found.setdefault("quantidade", i)
        elif "total" in h:
            found.setdefault("total", i)
        elif h.startswith("m.o") or h.startswith("mao") or "mão" in h or h == "mo":
            found.setdefault("mo", i)
        elif h.startswith("mat"):
            found.setdefault("material", i)
    idx.update(found)
    return idx


def _parse_orcamento_rows(rows: list[tuple], header_idx: int) -> list[dict]:
    """Planilha de orcamento: etapa = codigo 2 digitos (A), servico = XX.YY (A) com valores.

    Colunas mapeadas pelo CABECALHO (ITEM, DESCRICAO, UNIDADE, QTD, M.O, MAT, [EQUIP], TOTAL); a
    coluna EQUIP e OPCIONAL. Ignora sub-rotulos (so B), SUBTOTAL/TOTAL e notas. Dedupe nome_norm.
    'ambiente' fica None. 'custo_equipamento' so o modulo de orcamento usa (o checklist ignora).
    """
    col = _orcamento_cols(rows[header_idx] if header_idx < len(rows) else ())
    etapas: dict[str, dict] = {}
    last: str | None = None
    ordem_e = 0

    for r in rows[header_idx + 1 :]:
        a = _cell(r, col["item"])
        b = _cell(r, col["descricao"])
        if not a and not b:
            continue
        au = a.upper()
        if au.startswith("SUBTOTAL") or au.startswith("TOTAL"):
            continue

        if _RE_ETAPA.match(a):
            if not b:
                continue
            nn = norm_nome(b)
            if not nn:
                continue
            if nn not in etapas:
                ordem_e += 1
                etapas[nn] = {
                    "nome": b, "nome_norm": nn, "ordem": ordem_e, "itens": {}, "_oi": 0
                }
            last = nn
            continue

        if _RE_ITEM.match(a):
            if last is None or not b:
                continue  # servico antes de qualquer etapa (raro) ou sem descricao -> ignora
            inn = norm_nome(b)
            if not inn:
                continue
            et = etapas[last]
            if inn in et["itens"]:
                continue
            et["_oi"] += 1
            et["itens"][inn] = {
                "nome": b,
                "nome_norm": inn,
                "ordem": et["_oi"],
                "ambiente": None,
                "unidade": _cell(r, col["unidade"]) or None,
                "quantidade": _num(_at(r, col["quantidade"])),
                "custo_mao_obra": _num(_at(r, col["mo"])),
                "custo_material": _num(_at(r, col["material"])),
                "custo_equipamento": _num(_at(r, col["equipamento"])),
                "custo_total": _num(_at(r, col["total"])),
            }
            continue
        # sub-rotulo (so B), notas, escopo, pagamento -> ignora

    return [
        {
            "nome": e["nome"],
            "nome_norm": e["nome_norm"],
            "ordem": e["ordem"],
            "itens": list(e["itens"].values()),
        }
        for e in etapas.values()
    ]
