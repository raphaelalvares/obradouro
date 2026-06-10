"""Testes do Catálogo (Livro de referências · Fatia 1) — foco na MATEMÁTICA do unitário (sem banco).

Invariante: o catálogo guarda custo UNITÁRIO (4 casas); o orçamento guarda subtotal (2 casas).
- promover: unit = subtotal / qtd  (qtd ausente/0 → /1).
- aplicar (Fatia 2): subtotal = round(unit × qtd, 2).
O unitário é REFERÊNCIA: re-aplicar fecha em centavos p/ qtd pequena/moderada; p/ qtd grande o
desvio é LIMITADO por ~qtd×5e-5 (erro das 4 casas) — aceitável p/ estimativa, não é valor contábil.
"""

import pytest
from fastapi import HTTPException

from app.services.catalogo import _custo_unit, _custos_unit


def test_custo_unit_divide_pela_quantidade():
    assert _custo_unit(600, 1) == 600.0
    assert _custo_unit(7500, 75) == 100.0
    assert _custo_unit(0, 50) == 0.0


def test_custo_unit_qtd_ausente_ou_zero_trata_como_um():
    # verba / linha sem quantidade → a linha inteira é o "unitário".
    assert _custo_unit(900, None) == 900.0
    assert _custo_unit(900, 0) == 900.0
    assert _custo_unit(900, -3) == 900.0  # qtd negativa (defensivo) → /1


def test_custo_unit_valor_nulo():
    assert _custo_unit(None, 50) == 0.0


def test_custo_unit_arredonda_a_4_casas():
    assert _custo_unit(5000, 75) == 66.6667   # 66.66666… → 4 casas
    assert _custo_unit(100, 3) == 33.3333
    assert _custo_unit(100, 7) == 14.2857


def test_round_trip_qtd_moderada_fecha_em_centavos():
    """Para qtd pequena/moderada (≤ ~100) as 4 casas bastam p/ o ida-e-volta fechar EM CENTAVOS."""
    for subtotal, qtd in [(5000, 75), (100, 3), (100, 7), (1234.56, 12), (87368, 23)]:
        unit = _custo_unit(subtotal, qtd)
        de_volta = round(unit * qtd, 2)
        assert abs(de_volta - round(subtotal, 2)) <= 0.01, (subtotal, qtd, unit, de_volta)


def test_round_trip_qtd_grande_drift_limitado_por_qtd():
    """Para qtd grande/fracionária o unitário é REFERÊNCIA: re-aplicar pode diferir do subtotal
    original, mas o desvio é LIMITADO por ~qtd×5e-5 (erro de arredondamento das 4 casas)."""
    for subtotal, qtd in [(1_234_567.89, 50_000), (2_809_639.80, 49_980.562), (9_999.99, 1250.5)]:
        unit = _custo_unit(subtotal, qtd)
        drift = abs(round(unit * qtd, 2) - round(subtotal, 2))
        assert drift <= qtd * 5e-5 + 0.01, (subtotal, qtd, unit, drift)


def test_custos_unit_valida_teto_evita_overflow():
    """_custos_unit calcula os 3 unitários e barra o que estoura o numeric(14,4) com 422 (não 500).
    Dividir por qtd < 1 amplifica: valor dentro do teto + qtd minúscula pode cruzar o limite."""
    assert _custos_unit(5000, 0, 0, 75) == (66.6667, 0.0, 0.0)
    assert _custos_unit(900, 600, 300, None) == (900.0, 600.0, 300.0)
    with pytest.raises(HTTPException) as exc:
        _custos_unit(10_000_000, 0, 0, 0.001)  # 1e7 / 1e-3 = 1e10 > teto
    assert exc.value.status_code == 422
