"""Trava o contrato msg↔parser do soft-limit ('limite_obras_ativas:<lim>:<atual>')."""

from app.core.problems import LimiteAtivasError, limite_from_exc


class _Orig:
    def __init__(self, msg: str):
        self._m = msg

    def __str__(self) -> str:
        return self._m


class _Exc(Exception):
    def __init__(self, msg: str):
        self.orig = _Orig(msg)


def test_parse_limite_ok():
    err = limite_from_exc(_Exc("limite_obras_ativas:1:1"))
    assert isinstance(err, LimiteAtivasError)
    assert err.limite == 1
    assert err.atual == 1


def test_parse_limite_com_contexto_pgsql():
    err = limite_from_exc(_Exc("limite_obras_ativas:5:7\nCONTEXT: PL/pgSQL function _checar..."))
    assert err.limite == 5
    assert err.atual == 7


def test_parse_limite_none_para_outro_erro():
    assert limite_from_exc(_Exc("connection reset by peer")) is None
