"""Testes do Orçamento (sem banco): matemática do unitário×quantidade, 'aplicar template' e pivot.

0068: valor_mo/material/equipamento = UNITÁRIO; subtotal (e bases dos totais) = valor × qtd.
_linha_do_template grava o unitário do catálogo; a quantidade vem do fator/área.
"""

from app.services.orcamentos import (
    _agrupar_ambientes,
    _aplicar_percentuais,
    _custo_direto_itens,
    _linha_do_template,
    _linha_excede_teto,
    _proposta_agrupar,
    _totais,
    _unit_do_import,
    _venda_item,
)


def test_unit_do_import_divide_subtotal_por_qtd():
    # planilha: M.O = SUBTOTAL de linha 5000, qtd 75 → unitário 66,6667 (÷75); reconstrói o TOTAL.
    lin = _unit_do_import(
        {"custo_mao_obra": 5000, "custo_material": None, "custo_equipamento": None,
         "quantidade": 75}
    )
    assert lin["quantidade"] == 75
    assert lin["valor_mo"] == 66.6667
    assert lin["valor_material"] == 0.0
    assert round(lin["valor_mo"] * 75, 2) == 5000.0  # subtotal reconstruído = TOTAL


def test_unit_do_import_verba_qtd_um():
    lin = _unit_do_import(
        {"custo_mao_obra": None, "custo_material": 600, "custo_equipamento": None, "quantidade": 1}
    )
    assert lin["quantidade"] == 1
    assert lin["valor_material"] == 600.0


def test_unit_do_import_qtd_negativa_vira_verba():
    # qtd negativa (digitação no .xlsx) → verba (None), divide por 1 (não por -5).
    lin = _unit_do_import(
        {"custo_mao_obra": 100, "custo_material": None, "custo_equipamento": None, "quantidade": -5}
    )
    assert lin["quantidade"] is None
    assert lin["valor_mo"] == 100.0


def test_linha_template_fixa():
    linha = _linha_do_template(100, 50, 0, False, 2, None)
    assert linha["quantidade"] == 2
    assert linha["valor_mo"] == 100.0          # UNITÁRIO (não 200) — qtd fica no campo quantidade
    assert linha["valor_material"] == 50.0
    assert linha["valor_equipamento"] == 0.0


def test_linha_template_por_area_um_para_um():
    linha = _linha_do_template(85, 0, 0, True, 1.0, 20)  # piso: 1 m²/m² × 20 m²
    assert linha["quantidade"] == 20.0
    assert linha["valor_mo"] == 85.0           # unitário do catálogo, não 1700


def test_linha_template_coeficiente_por_area():
    linha = _linha_do_template(40, 10, 0, True, 2.5, 20)  # parede: 2,5 m²/m² × 20 = 50 m²
    assert linha["quantidade"] == 50.0
    assert linha["valor_mo"] == 40.0
    assert linha["valor_material"] == 10.0


def test_linha_template_unit_arredonda_4_casas():
    # o unitário arredonda a 4 casas (escala numeric(14,4)); a quantidade não o multiplica aqui.
    linha = _linha_do_template(66.66667, 0, 0, False, 3, None)
    assert linha["quantidade"] == 3
    assert linha["valor_mo"] == 66.6667


def test_linha_template_area_fracionaria():
    linha = _linha_do_template(100, 0, 0, True, 1, 12.5)
    assert linha["quantidade"] == 12.5
    assert linha["valor_mo"] == 100.0


def test_linha_template_sem_area_em_por_area_zera_qtd():
    # defensivo: por_area sem área → qtd 0 (o service barra com 422 antes). O unitário é preservado.
    linha = _linha_do_template(100, 0, 0, True, 1, None)
    assert linha["quantidade"] == 0.0
    assert linha["valor_mo"] == 100.0


def test_linha_excede_teto():
    # linha normal cabe; qtd ou unitário absurdos estouram o numeric (→ 422 no aplicar, não 500).
    assert _linha_excede_teto(_linha_do_template(100, 0, 0, True, 1, 20)) is False
    assert _linha_excede_teto(
        {"quantidade": 1e12, "valor_mo": 0, "valor_material": 0, "valor_equipamento": 0}
    ) is True  # qtd > numeric(14,3)
    assert _linha_excede_teto(
        {"quantidade": 1, "valor_mo": 1e15, "valor_material": 0, "valor_equipamento": 0}
    ) is True  # unitário > numeric(18,4)


def test_totais_multiplica_por_quantidade():
    # base por tipo = Σ (unitário × quantidade). Verba (qtd nula) conta como ×1.
    versao = {"maj_mo": 0, "maj_material": 0, "maj_equipamento": 0, "bdi": 0, "imposto": 0}
    itens = [
        {"valor_mo": 100, "valor_material": 50, "valor_equipamento": 0, "quantidade": 10},
        {"valor_mo": 5, "valor_material": 0, "valor_equipamento": 0, "quantidade": None},  # verba
    ]
    t = _totais(versao, itens)
    assert t["base_mo"] == 100 * 10 + 5  # 1005
    assert t["base_material"] == 50 * 10  # 500
    assert t["custo_direto"] == 1505.0


def test_totais_quantidade_zero_conta_como_verba():
    # qtd 0 = verba (não zera a linha) → ×1, igual à conversão da migration (não divide por 0).
    versao = {"maj_mo": 0, "maj_material": 0, "maj_equipamento": 0, "bdi": 0, "imposto": 0}
    item = {"valor_mo": 80, "valor_material": 0, "valor_equipamento": 0, "quantidade": 0}
    t = _totais(versao, [item])
    assert t["base_mo"] == 80.0


def test_custo_direto_itens_por_etapa_usa_quantidade():
    versao = {"maj_mo": 10, "maj_material": 0, "maj_equipamento": 0}
    itens = [{"valor_mo": 100, "valor_material": 0, "valor_equipamento": 0, "quantidade": 4}]
    # (100 × 4) × 1,10 = 440
    assert round(_custo_direto_itens(versao, itens), 2) == 440.0


def test_aplicar_percentuais_exemplo_planejamento():
    # exemplo travado do plano: custo direto 10.650 × (1+BDI 20%) × (1+imposto 10%) = 14.058.
    r = _aplicar_percentuais(10650, 0, 0, 0, 0, 0, 20, 10)
    assert r["custo_direto"] == 10650.0
    assert round(r["preco_final"], 2) == 14058.0


def test_aplicar_percentuais_majoracao_por_tipo():
    # base 1000 M.O com 10% de majoração → 1100 de custo direto; sem BDI/imposto → preço = 1100.
    r = _aplicar_percentuais(1000, 0, 0, 10, 0, 0, 0, 0)
    assert r["custo_direto"] == 1100.0
    assert r["preco_final"] == 1100.0


def test_central_usa_a_mesma_formula_que_totais():
    # a central soma as bases em SQL e aplica _aplicar_percentuais; tem de bater com _totais (que
    # soma os itens em Python) → garante consistência entre as duas telas (mesmos números).
    versao = {"maj_mo": 10, "maj_material": 5, "maj_equipamento": 0, "bdi": 20, "imposto": 8}
    itens = [
        {"valor_mo": 3000, "valor_material": 2000, "valor_equipamento": 500, "quantidade": 1},
        {"valor_mo": 1000, "valor_material": 0, "valor_equipamento": 1500, "quantidade": 1},
    ]
    t = _totais(versao, itens)
    # bases somadas (qtd 1): (3000+1000, 2000+0, 500+1500)
    central = _aplicar_percentuais(4000, 2000, 2000, 10, 5, 0, 20, 8)
    assert round(central["custo_direto"], 2) == round(t["custo_direto"], 2)
    assert round(central["preco_final"], 2) == round(t["preco_final"], 2)


def test_venda_soma_das_linhas_bate_com_preco_final():
    # a fórmula do preço é linear nos itens → Σ _venda_item == totais.preco_final (a proposta do
    # cliente mostra os MESMOS números da tela do arquiteto, distribuídos por linha).
    versao = {"maj_mo": 10, "maj_material": 5, "maj_equipamento": 0, "bdi": 20, "imposto": 8}
    itens = [
        {"etapa": "A", "ordem_etapa": 1, "descricao": "x", "valor_mo": 100, "valor_material": 50,
         "valor_equipamento": 10, "quantidade": 4},
        {"etapa": "B", "ordem_etapa": 2, "descricao": "y", "valor_mo": 7, "valor_material": 0,
         "valor_equipamento": 0, "quantidade": None},  # verba → ×1
    ]
    t = _totais(versao, itens)
    soma = sum(_venda_item(versao, i) for i in itens)
    assert round(soma, 6) == round(t["preco_final"], 6)


def test_venda_item_aplica_percentuais_na_linha():
    versao = {"maj_mo": 10, "maj_material": 0, "maj_equipamento": 0, "bdi": 20, "imposto": 10}
    item = {"valor_mo": 100, "valor_material": 0, "valor_equipamento": 0, "quantidade": None}
    # 100 × 1,10 (maj) × 1,20 (BDI) × 1,10 (imposto) = 145,20
    assert round(_venda_item(versao, item), 2) == 145.20


def test_proposta_agrupar_soma_e_ordena():
    # agrupa linhas de venda (já calculadas no SQL) por etapa; ordem = menor ordem_etapa; só venda.
    rows = [
        {"etapa": "Pintura", "ordem_etapa": 2, "descricao": "Parede", "ordem": 1,
         "ambiente": "Sala", "unidade": "m²", "quantidade": 10, "valor": 150.0},
        {"etapa": "Demolição", "ordem_etapa": 1, "descricao": "Piso", "ordem": 1,
         "ambiente": None, "unidade": None, "quantidade": None, "valor": 80.0},
        {"etapa": "Pintura", "ordem_etapa": 2, "descricao": "Teto", "ordem": 2,
         "ambiente": None, "unidade": None, "quantidade": None, "valor": 100.0},
    ]
    grupos = _proposta_agrupar(rows)
    assert [g["etapa"] for g in grupos] == ["Demolição", "Pintura"]  # por ordem_etapa
    assert grupos[1]["valor"] == 250.0  # 150 + 100
    item = grupos[1]["itens"][0]
    assert set(item) == {"descricao", "ambiente", "unidade", "quantidade", "valor"}  # só venda


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
    assert grupos[-1]["custo_direto"] == 50.0  # sem quantidade → ×1
