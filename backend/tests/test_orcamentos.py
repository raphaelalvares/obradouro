"""Testes do Orçamento — Fatia 2 (sem banco): matemática do 'aplicar template' e pivot por cômodo.

aplicar: qtd = por_area ? round(fator×área, 3) : fator; subtotal = round(custo_unit × qtd, 2).
"""

from app.services.orcamentos import _agrupar_ambientes, _linha_do_template, _linha_excede_teto


def test_linha_template_fixa():
    linha = _linha_do_template(100, 50, 0, False, 2, None)
    assert linha["quantidade"] == 2
    assert linha["valor_mo"] == 200.0
    assert linha["valor_material"] == 100.0
    assert linha["valor_equipamento"] == 0.0


def test_linha_template_por_area_um_para_um():
    linha = _linha_do_template(85, 0, 0, True, 1.0, 20)  # piso: 1 m²/m² × 20 m²
    assert linha["quantidade"] == 20.0
    assert linha["valor_mo"] == 1700.0


def test_linha_template_coeficiente_por_area():
    linha = _linha_do_template(40, 10, 0, True, 2.5, 20)  # parede: 2,5 m²/m² × 20 = 50 m²
    assert linha["quantidade"] == 50.0
    assert linha["valor_mo"] == 2000.0
    assert linha["valor_material"] == 500.0


def test_linha_template_subtotal_arredonda_2_casas():
    # custo unitário de 4 casas × qtd → subtotal arredonda a 2 casas (escala do orcamento_itens).
    linha = _linha_do_template(66.6667, 0, 0, False, 3, None)
    assert linha["valor_mo"] == 200.0  # 66.6667 × 3 = 200.0001 → 200.00


def test_linha_template_area_fracionaria():
    linha = _linha_do_template(100, 0, 0, True, 1, 12.5)
    assert linha["quantidade"] == 12.5
    assert linha["valor_mo"] == 1250.0


def test_linha_template_sem_area_em_por_area_zera():
    # defensivo: por_area sem área → qtd 0 (o service barra isso com 422 antes de chegar aqui).
    linha = _linha_do_template(100, 0, 0, True, 1, None)
    assert linha["quantidade"] == 0.0
    assert linha["valor_mo"] == 0.0


def test_linha_excede_teto():
    # linha normal cabe; qtd ou subtotal absurdos estouram o numeric (→ 422 no aplicar, não 500).
    assert _linha_excede_teto(_linha_do_template(100, 0, 0, True, 1, 20)) is False
    assert _linha_excede_teto(
        {"quantidade": 1e12, "valor_mo": 0, "valor_material": 0, "valor_equipamento": 0}
    ) is True  # qtd > numeric(14,3)
    assert _linha_excede_teto(
        {"quantidade": 1, "valor_mo": 1e13, "valor_material": 0, "valor_equipamento": 0}
    ) is True  # subtotal > numeric(14,2)


def test_agrupar_ambientes_geral_por_ultimo():
    versao = {"maj_mo": 0, "maj_material": 0, "maj_equipamento": 0}
    itens = [
        {"ambiente": "Cozinha", "valor_mo": 100, "valor_material": 0, "valor_equipamento": 0},
        {"ambiente": None, "valor_mo": 50, "valor_material": 0, "valor_equipamento": 0},
        {"ambiente": "Banheiro", "valor_mo": 30, "valor_material": 0, "valor_equipamento": 0},
    ]
    grupos = _agrupar_ambientes(versao, itens)
    # ordenado por nome; "Geral" (None) por último
    assert [g["ambiente"] for g in grupos] == ["Banheiro", "Cozinha", None]
    assert grupos[-1]["custo_direto"] == 50.0
