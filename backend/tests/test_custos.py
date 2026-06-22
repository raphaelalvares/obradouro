"""Testes da derivação de custo (sem banco). Função pura derivar_custos:
material = quantidade × valor_unitario (senão custo_material_in legado); total = MO + material, ou o
custo_total_in quando vier explícito (override do usuário)."""

from app.services.checklist import derivar_custos


def test_material_qtd_x_unit():
    mat, tot = derivar_custos(10, 5, None)
    assert mat == 50.0
    assert tot == 50.0  # sem MO → total = material


def test_total_mo_mais_material():
    mat, tot = derivar_custos(10, 5, 20)
    assert mat == 50.0
    assert tot == 70.0  # MO 20 + material 50


def test_verba_qtd1():
    # lump-sum: unidade "vb", qtd 1, valor_unitario = valor → material = valor.
    mat, tot = derivar_custos(1, 3000, None)
    assert mat == 3000.0
    assert tot == 3000.0


def test_mo_apenas():
    mat, tot = derivar_custos(None, None, 800)
    assert mat is None
    assert tot == 800.0


def test_tudo_vazio():
    assert derivar_custos(None, None, None) == (None, None)


def test_override_total():
    # usuário sobrescreve o total → vale o override, material ainda deriva da metragem.
    mat, tot = derivar_custos(10, 5, 20, custo_total_in=200)
    assert mat == 50.0
    assert tot == 200.0


def test_material_legado_sem_unit():
    # sem quantidade/valor_unitario → respeita o custo_material digitado direto (legado).
    mat, tot = derivar_custos(None, None, None, custo_material_in=300)
    assert mat == 300.0
    assert tot == 300.0


def test_computado_vence_material_legado():
    # com quantidade × valor_unitario, o material computado IGNORA o custo_material_in.
    mat, tot = derivar_custos(2, 10, None, custo_material_in=999)
    assert mat == 20.0
    assert tot == 20.0


def test_arredonda_2_casas():
    mat, _ = derivar_custos(0.1, 0.2, None)  # 0.1*0.2 = 0.0200000…4 em float
    assert mat == 0.02


def test_so_quantidade_sem_unit_nao_deriva_material():
    # quantidade sem valor_unitario (e sem material legado) → material None; total só do MO.
    mat, tot = derivar_custos(10, None, 100)
    assert mat is None
    assert tot == 100.0
