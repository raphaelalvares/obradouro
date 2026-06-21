"""Testes do avanço por tarefa do diário (sem banco). Foco na derivação pura do %."""

from app.services.diario_tarefa import derivar_pct


def test_derivar_por_quantidade():
    assert derivar_pct(5, 10, None) == 50.0
    assert derivar_pct(3, 4, None) == 75.0


def test_derivar_quantidade_clampa_em_100():
    # executou mais que o total (re-medição/erro) → trava em 100.
    assert derivar_pct(15, 10, None) == 100.0


def test_derivar_quantidade_arredonda_2_casas():
    assert derivar_pct(1, 3, None) == 33.33


def test_derivar_usa_pct_quando_sem_quantidade():
    # tarefa sem total planejado → usa o % informado direto.
    assert derivar_pct(None, None, 30) == 30.0
    assert derivar_pct(None, 0, 42.5) == 42.5  # quantidade 0 não serve de base


def test_derivar_pct_tem_prioridade_da_quantidade():
    # se há quantidade(>0) E qtd executada, deriva da quantidade (ignora o pct informado).
    assert derivar_pct(2, 8, 99) == 25.0


def test_derivar_clampa_negativo_e_acima():
    assert derivar_pct(None, None, -5) == 0.0
    assert derivar_pct(None, None, 150) == 100.0


def test_derivar_degenerado_sem_base_e_sem_pct():
    # só qtd, sem total e sem pct → 0 (o front só oferece entrada por qtd quando há quantidade).
    assert derivar_pct(7, None, None) == 0.0
