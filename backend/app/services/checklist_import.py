"""Parser do template .xlsx de import + normalizacao de nome (chave de dedupe).

`norm_nome` e o CONTRATO CONGELADO da chave natural: e gravado em etapas/checklist_itens.nome_norm
tanto no create manual quanto no import, e os unique indexes (obra,nome_norm)/(etapa,nome_norm)
fazem o dedupe. Por isso ele dobra acento e forma Unicode (NFKD + remove diacriticos + casefold +
colapsa espacos): 'Fundação', 'Fundacao' e 'Fundaçao' (cedilha combinante) viram a MESMA chave.
"""

import io
import re
import unicodedata

from fastapi import HTTPException, status

MAX_XLSX_BYTES = 2 * 1024 * 1024  # guarda anti zip-bomb / arquivo gigante
MAX_LINHAS = 5000
# colunas FIXAS (poka-yoke: "nao e qualquer Excel"); validadas exatas no cabecalho.
TEMPLATE_HEADER = ("etapa", "item", "ordem_etapa", "ordem_item")


def norm_nome(s: str) -> str:
    """Chave de dedupe (contrato congelado). NFKD -> sem diacritico -> casefold -> 1 espaco."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))  # remove acentos/diacriticos
    return re.sub(r"\s+", " ", s).strip().casefold()


def parse_template(raw: bytes) -> list[dict]:
    """Le o .xlsx do template e devolve a arvore [{nome,nome_norm,ordem,itens:[...]}].

    Rejeita (422) arquivo fora do padrao e NAO descarta linhas em silencio: item sem etapa vira erro
    com o numero da linha (evita "import comeu meus dados"). Dedupe DENTRO do arquivo: 1a ocorrencia
    de cada (etapa)/(etapa,item) vence; as repetidas sao ignoradas (mesmo no = mesma linha logica).
    """
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

    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    header = tuple(
        (str(c).strip().lower() if c is not None else "") for c in (next(rows, ()) or ())
    )
    if header[: len(TEMPLATE_HEADER)] != TEMPLATE_HEADER:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "template fora do padrao (cabecalho esperado: etapa, item, ordem_etapa, ordem_item)",
        )

    etapas: dict[str, dict] = {}  # nome_norm -> {nome, nome_norm, ordem, itens: {item_norm: {...}}}
    last_etapa: str | None = None
    erros: list[str] = []
    linha = 1  # cabecalho ja consumido

    for r in rows:
        linha += 1
        if linha - 1 > MAX_LINHAS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "template excede o limite de linhas"
            )
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


def _as_int(v: object) -> int:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
