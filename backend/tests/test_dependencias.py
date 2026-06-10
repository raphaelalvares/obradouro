"""Testes da Fatia B (dependências) sem banco: forward pass do recálculo (função `planejar`)."""

from datetime import date

import pytest

from app.services.dependencias import _dur, planejar


def _t(di=None, df=None, dur=None) -> dict:
    return {"data_inicio": di, "data_fim": df, "duracao_dias": dur}


def _aresta(p, s, lag=0) -> dict:
    return {"predecessora_id": p, "sucessora_id": s, "lag_dias": lag}


# ---------------- _dur (duração efetiva da tarefa) ----------------
def test_dur_preferencia_e_fallback():
    assert _dur(_t(dur=5)) == 5  # duracao_dias manda
    assert _dur(_t(di=date(2026, 1, 1), df=date(2026, 1, 3))) == 3  # span inclusivo
    assert _dur(_t()) == 1  # sem nada → 1 dia
    assert _dur(_t(dur=0)) == 1  # 0/negativo → no mínimo 1


# ---------------- planejar: cadeia simples ----------------
def test_cadeia_encadeia_datas():
    tarefas = {
        "a": _t(di=date(2026, 1, 1), dur=3),  # cabeça: usa o próprio início
        "b": _t(dur=2),
        "c": _t(dur=1),
    }
    plano = planejar(tarefas, [_aresta("a", "b"), _aresta("b", "c")], date(2026, 1, 1))
    assert plano["a"] == (date(2026, 1, 1), date(2026, 1, 3))  # 1..3 (3 dias)
    assert plano["b"] == (date(2026, 1, 4), date(2026, 1, 5))  # dia seguinte ao fim de A
    assert plano["c"] == (date(2026, 1, 6), date(2026, 1, 6))  # dia seguinte ao fim de B


def test_cabeca_sem_data_usa_ancora():
    tarefas = {"a": _t(dur=2), "b": _t(dur=2)}
    plano = planejar(tarefas, [_aresta("a", "b")], date(2026, 3, 10))
    assert plano["a"] == (date(2026, 3, 10), date(2026, 3, 11))
    assert plano["b"] == (date(2026, 3, 12), date(2026, 3, 13))


def test_folga_lag_empurra_sucessora():
    tarefas = {"a": _t(di=date(2026, 1, 1), dur=1), "b": _t(dur=1)}
    plano = planejar(tarefas, [_aresta("a", "b", lag=3)], date(2026, 1, 1))
    # A termina 01/01; sucessora = fim + 1 + folga(3) = 05/01
    assert plano["b"] == (date(2026, 1, 5), date(2026, 1, 5))


def test_dois_predecessores_pega_o_maior_fim():
    tarefas = {
        "a": _t(di=date(2026, 1, 1), dur=2),  # fim 02/01
        "b": _t(di=date(2026, 1, 1), dur=5),  # fim 05/01 (manda)
        "c": _t(dur=1),
    }
    plano = planejar(tarefas, [_aresta("a", "c"), _aresta("b", "c")], date(2026, 1, 1))
    assert plano["c"] == (date(2026, 1, 6), date(2026, 1, 6))  # dia seguinte ao MAIOR fim


def test_tarefa_solta_fica_de_fora():
    # 'z' não aparece em nenhuma aresta → não entra no plano (mantém datas manuais)
    tarefas = {"a": _t(di=date(2026, 1, 1), dur=1), "b": _t(dur=1), "z": _t(dur=9)}
    plano = planejar(tarefas, [_aresta("a", "b")], date(2026, 1, 1))
    assert "z" not in plano
    assert set(plano) == {"a", "b"}


def test_ciclo_levanta_valueerror():
    tarefas = {"a": _t(dur=1), "b": _t(dur=1)}
    with pytest.raises(ValueError):
        planejar(tarefas, [_aresta("a", "b"), _aresta("b", "a")], date(2026, 1, 1))
