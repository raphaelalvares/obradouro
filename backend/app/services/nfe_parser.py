"""Parser de NF-e (XML) — extrai produtos/qtds/valores p/ o estoque. SEM cunho fiscal: lemos só o
que interessa ao controle de obra. Robusto a namespace (a NF-e usa
`http://www.portalfiscal.inf.br/nfe`) via casamento por *local-name*. Aceita o XML cru da NF-e
(`<NFe>`) ou o de processamento (`<nfeProc>`).
"""

import re

import defusedxml.ElementTree as ET
from defusedxml.common import DefusedXmlException


class NFeParseError(ValueError):
    """XML inválido ou que não parece uma NF-e."""


def _local(tag: str) -> str:
    """Tira o namespace: '{http://...}infNFe' -> 'infNFe'."""
    return tag.rsplit("}", 1)[-1]


def _first(el, name: str):
    """1º descendente (inclui o próprio) com aquele local-name, ou None."""
    if el is None:
        return None
    for c in el.iter():
        if _local(c.tag) == name:
            return c
    return None


def _all(el, name: str) -> list:
    return [c for c in el.iter() if _local(c.tag) == name] if el is not None else []


def _txt(el, name: str) -> str | None:
    c = _first(el, name)
    if c is None or c.text is None:
        return None
    t = c.text.strip()
    return t or None


def _num(s: str | None) -> float | None:
    """Decimal da NF-e usa '.' (padrão XML). Devolve float ou None."""
    if s is None:
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_nfe(raw: bytes) -> dict:
    """Devolve dict com chave/numero/serie/emitente/data_emissao/valor_total + itens[].
    Levanta NFeParseError se não for XML válido, não for NF-e, ou faltar a chave de 44 dígitos."""
    try:
        # defusedxml: bloqueia expansão de entidades (billion laughs) e refs externas (XXE).
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise NFeParseError("arquivo não é um XML válido") from e
    except DefusedXmlException as e:
        raise NFeParseError("XML com construção não permitida (entidade/DTD externa)") from e

    inf = _first(root, "infNFe")
    if inf is None:
        raise NFeParseError("XML não parece uma NF-e (sem infNFe)")

    # chave = atributo Id ("NFe" + 44 dígitos)
    chave_raw = inf.get("Id") or ""
    digitos = re.sub(r"\D", "", chave_raw)
    if len(digitos) < 44:
        raise NFeParseError("chave de acesso da NF-e não encontrada")
    chave = digitos[-44:]

    ide = _first(inf, "ide")
    emit = _first(inf, "emit")
    total = _first(inf, "total")

    itens: list[dict] = []
    for idx, det in enumerate(_all(inf, "det"), start=1):
        prod = _first(det, "prod")
        if prod is None:
            continue
        n_item = det.get("nItem")
        itens.append(
            {
                "codigo": _txt(prod, "cProd"),
                "descricao": _txt(prod, "xProd") or "(sem descrição)",
                "ncm": _txt(prod, "NCM"),
                "unidade": _txt(prod, "uCom"),
                "quantidade_nota": _num(_txt(prod, "qCom")),
                "valor_unitario": _num(_txt(prod, "vUnCom")),
                "valor_total": _num(_txt(prod, "vProd")),
                "ordem": int(n_item) if (n_item and n_item.isdigit()) else idx,
            }
        )

    return {
        "chave": chave,
        "numero": _txt(ide, "nNF"),
        "serie": _txt(ide, "serie"),
        "emitente_nome": _txt(emit, "xNome"),
        "emitente_cnpj": _txt(emit, "CNPJ"),
        # dhEmi (com fuso) ou dEmi (data antiga); o banco faz ::timestamptz
        "data_emissao": _txt(ide, "dhEmi") or _txt(ide, "dEmi"),
        "valor_total": _num(_txt(total, "vNF")),
        "itens": itens,
    }
