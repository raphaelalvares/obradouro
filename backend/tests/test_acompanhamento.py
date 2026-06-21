"""Testes da curva S / avanço (Fatia C, sem banco). Foco na função pura curva_s.

planejado(D) = Σ peso das tarefas com data_fim <= D ; real(D) = Σ peso das concluídas até D.
Peso = custo quando a obra tem custos; senão contagem (1 por tarefa).
"""

import datetime as dt

from app.services.acompanhamento import curva_s

D = dt.date


def _t(di, df, concl, cem, peso=None):
    return {
        "peso_custo": peso,
        "data_inicio": di,
        "data_fim": df,
        "concluido": concl,
        "concluido_em": cem,
    }


def test_vazio():
    r = curva_s([], D(2026, 6, 1))
    assert r["peso_total"] == 0.0
    assert r["real_pct"] == 0.0
    assert r["pontos"] == []


def test_contagem_quando_sem_custos():
    tarefas = [
        _t(D(2026, 1, 1), D(2026, 1, 31), True, D(2026, 1, 20)),
        _t(D(2026, 2, 1), D(2026, 2, 28), False, None),
    ]
    r = curva_s(tarefas, D(2026, 2, 15))
    assert r["por_custo"] is False
    assert r["peso_total"] == 2.0
    assert r["real_pct"] == 50.0       # T1 concluída (1 de 2)
    assert r["planejado_pct"] == 50.0  # só T1 tinha término <= 15/02
    assert r["inicio"] == D(2026, 1, 1)
    assert r["fim"] == D(2026, 2, 28)


def test_ponderado_por_custo():
    tarefas = [
        _t(D(2026, 1, 1), D(2026, 1, 31), True, D(2026, 1, 20), peso=3000),
        _t(D(2026, 2, 1), D(2026, 2, 28), False, None, peso=1000),
    ]
    r = curva_s(tarefas, D(2026, 2, 15))
    assert r["por_custo"] is True
    assert r["peso_total"] == 4000.0
    assert r["real_pct"] == 75.0       # 3000/4000
    assert r["planejado_pct"] == 75.0


def test_real_nao_conta_conclusao_futura():
    # tarefa concluída DEPOIS de hoje não entra no realizado de hoje (curva histórica correta).
    tarefas = [_t(D(2026, 1, 1), D(2026, 1, 31), True, D(2026, 3, 10), peso=100)]
    r = curva_s(tarefas, D(2026, 2, 1))
    assert r["planejado_pct"] == 100.0  # término 31/01 <= 01/02
    assert r["real_pct"] == 0.0         # concluída só em 10/03


def test_concluida_sem_data_conta_como_hoje():
    # anomalia: concluído sem carimbo → conta como concluído HOJE (não some do realizado atual).
    tarefas = [_t(D(2026, 1, 1), D(2026, 1, 31), True, None, peso=100)]
    r = curva_s(tarefas, D(2026, 2, 1))
    assert r["real_pct"] == 100.0


def test_obra_mista_cai_para_contagem():
    # algumas tarefas SEM custo → NÃO pondera por custo (senão as sem-custo pesariam 0 e sumiriam,
    # escondendo progresso real). Cai p/ contagem (cada tarefa = 1).
    tarefas = [
        _t(D(2026, 1, 1), D(2026, 1, 31), True, D(2026, 1, 20), peso=1000),  # com custo, feita
        _t(D(2026, 2, 1), D(2026, 2, 28), True, D(2026, 2, 10), peso=None),  # sem custo, feita
        _t(D(2026, 3, 1), D(2026, 3, 31), False, None, peso=None),           # sem custo, pendente
    ]
    r = curva_s(tarefas, D(2026, 4, 1))
    assert r["por_custo"] is False
    assert r["peso_total"] == 3.0
    assert r["real_pct"] == round(2 / 3 * 100, 1)  # 2 de 3 feitas


def _tm(di, df, meds, peso=None, concl=False, cem=None):
    """Folha COM medições do diário ([{data, pct}]) — o avanço SNAPSHOT datado."""
    return {
        "peso_custo": peso,
        "data_inicio": di,
        "data_fim": df,
        "concluido": concl,
        "concluido_em": cem,
        "medicoes": meds,
    }


def test_curva_usa_medicoes_snapshot():
    # o "real" segue a ÚLTIMA medição até a data: 40% em 10/01, 80% em 20/01.
    tarefas = [
        _tm(D(2026, 1, 1), D(2026, 1, 31),
            [{"data": D(2026, 1, 10), "pct": 40}, {"data": D(2026, 1, 20), "pct": 80}], peso=100)
    ]
    r = curva_s(tarefas, D(2026, 1, 25))
    assert r["real_pct"] == 80.0
    by = {p["data"]: p for p in r["pontos"]}
    assert by[D(2026, 1, 10)]["real_pct"] == 40.0
    assert by[D(2026, 1, 20)]["real_pct"] == 80.0


def test_curva_medicao_parcial_ponderada_por_custo():
    tarefas = [
        _tm(D(2026, 1, 1), D(2026, 1, 31), [{"data": D(2026, 1, 15), "pct": 50}], peso=1000),
        _tm(D(2026, 2, 1), D(2026, 2, 28), [], peso=1000),  # sem medição → 0
    ]
    r = curva_s(tarefas, D(2026, 1, 20))
    assert r["por_custo"] is True
    assert r["real_pct"] == 25.0  # (1000*0.5 + 1000*0) / 2000


def test_curva_medicao_antes_da_data_nao_conta():
    tarefas = [_tm(D(2026, 1, 1), D(2026, 1, 31), [{"data": D(2026, 1, 20), "pct": 60}], peso=100)]
    r = curva_s(tarefas, D(2026, 1, 10))
    assert r["real_pct"] == 0.0  # a medição só aparece em 20/01


def test_curva_medicao_tem_prioridade_sobre_concluido_binario():
    # folha marcada concluída MAS com medição de 60% → vale a medição (não conta 100% binário).
    tarefas = [
        _tm(D(2026, 1, 1), D(2026, 1, 31), [{"data": D(2026, 1, 20), "pct": 60}],
            peso=100, concl=True, cem=D(2026, 1, 5))
    ]
    r = curva_s(tarefas, D(2026, 2, 1))
    assert r["real_pct"] == 60.0


def test_curva_estende_eixo_ate_conclusao_tardia():
    # obra atrasada: conclui DEPOIS do prazo. O eixo estende e o último ponto da curva real bate com
    # o "avanço real" do cabeçalho (antes a curva parava no término planejado e divergia).
    tarefas = [_t(D(2026, 1, 1), D(2026, 1, 31), True, D(2026, 3, 15), peso=100)]
    r = curva_s(tarefas, D(2026, 4, 1))
    assert r["real_pct"] == 100.0
    assert r["fim"] >= D(2026, 3, 15)
    assert r["pontos"][-1]["real_pct"] == 100.0
    assert r["planejado_pct"] == 100.0
