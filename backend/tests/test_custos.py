"""Testes da derivação de custo (sem banco). Função pura derivar_custos: composição UNITÁRIA —
material = quantidade × valor_unitario, mão de obra = quantidade × mao_obra_unitaria, total =
material + MO (ou custo_total_in quando explícito = override). Retorna (material, mo, total)."""

from app.services.checklist import derivar_custos


def test_material_qtd_x_unit():
    mat, mo, tot = derivar_custos(10, 5, None)
    assert mat == 50.0
    assert mo is None
    assert tot == 50.0  # sem MO → total = material


def test_total_material_mais_mo_unitaria():
    # MO também é UNITÁRIA: mão de obra = quantidade × mao_obra_unitaria.
    mat, mo, tot = derivar_custos(10, 5, 2)
    assert mat == 50.0
    assert mo == 20.0  # 10 × 2
    assert tot == 70.0  # material 50 + MO 20


def test_verba_qtd1():
    # lump-sum: unidade "vb", qtd 1, valor_unitario = valor → material = valor.
    mat, mo, tot = derivar_custos(1, 3000, None)
    assert mat == 3000.0
    assert mo is None
    assert tot == 3000.0


def test_mo_apenas_unitaria():
    # só MO unitária × quantidade (sem material).
    mat, mo, tot = derivar_custos(10, None, 8)
    assert mat is None
    assert mo == 80.0
    assert tot == 80.0


def test_tudo_vazio():
    assert derivar_custos(None, None, None) == (None, None, None)


def test_quantidade_sem_precos_nao_deriva():
    # quantidade sem nenhum preço unitário (e sem legado) → nada deriva.
    assert derivar_custos(10, None, None) == (None, None, None)


def test_override_total():
    # usuário sobrescreve o total → vale o override; material e MO ainda derivam dos unitários.
    mat, mo, tot = derivar_custos(10, 5, 2, custo_total_in=200)
    assert mat == 50.0
    assert mo == 20.0
    assert tot == 200.0


def test_material_legado_sem_unit():
    # sem quantidade/valor_unitario → respeita o custo_material legado (import sem unitário).
    mat, mo, tot = derivar_custos(None, None, None, custo_material_in=300)
    assert mat == 300.0
    assert mo is None
    assert tot == 300.0


def test_mo_legada_sem_unit():
    # sem quantidade/mao_obra_unitaria → respeita o custo_mao_obra legado.
    mat, mo, tot = derivar_custos(None, None, None, custo_mao_obra_in=120)
    assert mat is None
    assert mo == 120.0
    assert tot == 120.0


def test_computado_vence_legado():
    # com unitários, os totais computados IGNORAM os custos legados.
    mat, mo, tot = derivar_custos(2, 10, 5, custo_material_in=999, custo_mao_obra_in=999)
    assert mat == 20.0
    assert mo == 10.0
    assert tot == 30.0


def test_arredonda_material_2_casas():
    mat, _, _ = derivar_custos(0.1, 0.2, None)  # 0.1*0.2 = 0.0200000…4 em float
    assert mat == 0.02


def test_arredonda_mo_2_casas():
    _, mo, _ = derivar_custos(0.1, None, 0.2)
    assert mo == 0.02
