"""Testes do Catálogo (Livro de referências · Fatia 1) — foco na MATEMÁTICA do unitário (sem banco).

Invariante: o catálogo guarda custo UNITÁRIO (4 casas); o orçamento guarda subtotal (2 casas).
- promover: unit = subtotal / qtd  (qtd ausente/0 → /1).
- aplicar (Fatia 2): subtotal = round(unit × qtd, 2).
As 4 casas do unitário têm de bastar p/ o ida-e-volta fechar EM CENTAVOS (sem perder dinheiro).
"""

from app.services.catalogo import _custo_unit


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


def test_round_trip_fecha_em_centavos():
    """O drift do unitário a 4 casas tem de sumir ao voltar p/ subtotal a 2 casas."""
    for subtotal, qtd in [(5000, 75), (100, 3), (100, 7), (1234.56, 12), (87368, 23)]:
        unit = _custo_unit(subtotal, qtd)
        de_volta = round(unit * qtd, 2)
        assert abs(de_volta - round(subtotal, 2)) <= 0.01, (subtotal, qtd, unit, de_volta)
