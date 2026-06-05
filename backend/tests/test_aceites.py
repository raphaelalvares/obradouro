"""Aceite legal: versões vigentes, carimbo de todos os docs e cálculo de pendentes."""

import asyncio

from app.core.legal import DOCUMENTOS, PRIVACIDADE_VERSAO, TERMOS_VERSAO
from app.services import aceites


def test_documentos_versionados():
    assert DOCUMENTOS == {"termos": TERMOS_VERSAO, "privacidade": PRIVACIDADE_VERSAO}
    assert all(DOCUMENTOS.values())  # nenhuma versão vazia


class _Row:
    def __init__(self, documento: str, versao: str):
        self.documento = documento
        self.versao = versao


class _FakeResult:
    def __init__(self, rows: list | None = None):
        self._rows = rows or []

    def all(self):
        return self._rows


class _FakeSession:
    """Captura statements/params executados; devolve linhas pré-programadas nos SELECT."""

    def __init__(self, select_rows: list | None = None):
        self.execs: list[tuple[str, dict | None]] = []
        self._select_rows = select_rows or []

    async def execute(self, stmt, params=None):
        self.execs.append((str(stmt), params))
        return _FakeResult(self._select_rows if params is None else [])


def test_registrar_carimba_todos_os_documentos():
    session = _FakeSession()
    asyncio.run(aceites.registrar(session, "cadastro"))

    inserts = [p for _, p in session.execs if p and "documento" in p]
    assert {p["documento"] for p in inserts} == {"termos", "privacidade"}
    assert all(p["origem"] == "cadastro" for p in inserts)
    # versão carimbada = a vigente, não a que o cliente mandar
    assert {p["versao"] for p in inserts} == set(DOCUMENTOS.values())


def test_pendentes_sem_aceite_lista_todos():
    pend = asyncio.run(aceites.pendentes(_FakeSession(select_rows=[])))
    assert {p["documento"] for p in pend} == set(DOCUMENTOS)


def test_pendentes_com_versao_aceita_some_da_lista():
    aceitos = [_Row("termos", TERMOS_VERSAO)]  # só termos aceito na versão vigente
    pend = asyncio.run(aceites.pendentes(_FakeSession(select_rows=aceitos)))
    assert {p["documento"] for p in pend} == {"privacidade"}


def test_pendentes_versao_antiga_ainda_pende():
    aceitos = [_Row("termos", "1900-01-01"), _Row("privacidade", "1900-01-01")]
    pend = asyncio.run(aceites.pendentes(_FakeSession(select_rows=aceitos)))
    # versões antigas não cobrem a vigente → re-aceite pendente de ambos
    assert {p["documento"] for p in pend} == set(DOCUMENTOS)
