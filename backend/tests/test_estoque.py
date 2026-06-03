"""Fase 6 — unidade do que dá p/ testar sem DB: o parser de NF-e (XML → produtos/qtds/valores).
A idempotência (chave) e a divergência (conferência) vivem no banco/RPC (testadas em integração)."""

import pytest

from app.services.nfe_parser import NFeParseError, parse_nfe

# chave de 44 dígitos (cUF AAMM CNPJ mod serie nNF tpEmis cNF cDV)
_CHAVE = "35200114200166000187550010000000071000000017"

_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe{_CHAVE}" versao="4.00">
      <ide><nNF>7</nNF><serie>1</serie><dhEmi>2026-01-15T10:30:00-03:00</dhEmi></ide>
      <emit><CNPJ>14200166000187</CNPJ><xNome>Materiais de Construção LTDA</xNome></emit>
      <det nItem="1">
        <prod>
          <cProd>A123</cProd><xProd>Cimento CP-II 50kg</xProd><NCM>25232930</NCM>
          <uCom>SC</uCom><qCom>10.0000</qCom><vUnCom>32.5000000000</vUnCom><vProd>325.00</vProd>
        </prod>
      </det>
      <det nItem="2">
        <prod>
          <cProd>B456</cProd><xProd>Areia média</xProd>
          <uCom>M3</uCom><qCom>5.0000</qCom><vUnCom>120.0000000000</vUnCom><vProd>600.00</vProd>
        </prod>
      </det>
      <total><ICMSTot><vNF>925.00</vNF></ICMSTot></total>
    </infNFe>
  </NFe>
</nfeProc>"""


def test_parse_nfe_cabecalho():
    nfe = parse_nfe(_XML.encode("utf-8"))
    assert nfe["chave"] == _CHAVE
    assert len(nfe["chave"]) == 44
    assert nfe["numero"] == "7"
    assert nfe["serie"] == "1"
    assert nfe["emitente_nome"] == "Materiais de Construção LTDA"
    assert nfe["emitente_cnpj"] == "14200166000187"
    assert nfe["data_emissao"] == "2026-01-15T10:30:00-03:00"
    assert nfe["valor_total"] == 925.0


def test_parse_nfe_itens():
    nfe = parse_nfe(_XML.encode("utf-8"))
    assert len(nfe["itens"]) == 2
    a, b = nfe["itens"]
    assert a["codigo"] == "A123"
    assert a["descricao"] == "Cimento CP-II 50kg"
    assert a["ncm"] == "25232930"
    assert a["unidade"] == "SC"
    assert a["quantidade_nota"] == 10.0
    assert a["valor_unitario"] == 32.5
    assert a["valor_total"] == 325.0
    assert a["ordem"] == 1
    assert b["unidade"] == "M3"
    assert b["quantidade_nota"] == 5.0
    assert b["ncm"] is None  # ausente no XML
    assert b["ordem"] == 2


def test_parse_nfe_sem_nfeproc():
    # XML cru <NFe> (sem o wrapper de processamento) também é aceito
    inner = _XML[_XML.index("<NFe>") : _XML.index("</nfeProc>")]
    nfe = parse_nfe(inner.encode("utf-8"))
    assert nfe["chave"] == _CHAVE
    assert len(nfe["itens"]) == 2


def test_parse_nfe_xml_invalido():
    with pytest.raises(NFeParseError):
        parse_nfe(b"isto nao e xml")


def test_parse_nfe_sem_infnfe():
    with pytest.raises(NFeParseError):
        parse_nfe(b"<?xml version='1.0'?><raiz><x>1</x></raiz>")


def test_parse_nfe_sem_chave():
    xml = (
        '<NFe xmlns="http://www.portalfiscal.inf.br/nfe">'
        '<infNFe Id="NFe123"><ide/></infNFe></NFe>'
    )
    with pytest.raises(NFeParseError):
        parse_nfe(xml.encode("utf-8"))
