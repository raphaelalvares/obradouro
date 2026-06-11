"""Parser de NF-e (M4): defusedxml deve barrar billion-laughs/XXE e ainda parsear NF-e válida."""

import pytest

from app.services.nfe_parser import NFeParseError, parse_nfe

_BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<NFe><infNFe Id="x">&lol3;</infNFe></NFe>"""

_XXE = b"""<?xml version="1.0"?>
<!DOCTYPE r [ <!ENTITY x SYSTEM "file:///etc/passwd"> ]>
<NFe><infNFe Id="x">&x;</infNFe></NFe>"""

_NFE_OK = (
    '<?xml version="1.0"?><nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">'
    '<NFe><infNFe Id="NFe' + ("1" * 44) + '">'
    "<ide><nNF>123</nNF><serie>1</serie><dhEmi>2026-01-01T00:00:00-03:00</dhEmi></ide>"
    "<emit><xNome>FORNEC</xNome><CNPJ>00000000000191</CNPJ></emit>"
    "<det nItem=\"1\"><prod><cProd>A1</cProd><xProd>CIMENTO</xProd><uCom>SC</uCom>"
    "<qCom>10</qCom><vUnCom>30.00</vUnCom><vProd>300.00</vProd></prod></det>"
    "<total><ICMSTot><vNF>300.00</vNF></ICMSTot></total>"
    "</infNFe></NFe></nfeProc>"
).encode()


def test_billion_laughs_rejeitado_sem_expandir():
    with pytest.raises(NFeParseError):
        parse_nfe(_BILLION_LAUGHS)


def test_xxe_entidade_externa_rejeitado():
    with pytest.raises(NFeParseError):
        parse_nfe(_XXE)


def test_nfe_valida_parseia():
    r = parse_nfe(_NFE_OK)
    assert r["chave"] == "1" * 44
    assert r["emitente_nome"] == "FORNEC"
    assert len(r["itens"]) == 1
    assert r["itens"][0]["valor_total"] == 300.0
