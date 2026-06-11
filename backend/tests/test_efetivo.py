"""Testes "sem banco" da consolidação do efetivo do diário (Fatia C / 0067).

consolidar_efetivo é PURA: valida funcao_ids contra o mapa da obra, soma duplicatas (preservando a
ordem) e devolve (jsonb_str, total). O `nome` gravado é sempre o canônico do mapa (anti-tamper)."""

import json
import uuid

import pytest
from fastapi import HTTPException

from app.schemas.acompanhamento import EfetivoItem
from app.services.diario import consolidar_efetivo

PEDREIRO = uuid.uuid4()
SERVENTE = uuid.uuid4()
MESTRE = uuid.uuid4()
MAPA = {str(PEDREIRO): "Pedreiro", str(SERVENTE): "Servente", str(MESTRE): "Mestre de obras"}


def test_vazio_sem_total():
    assert consolidar_efetivo([], MAPA) == ("[]", None)


def test_item_unico():
    js, total = consolidar_efetivo([EfetivoItem(funcao_id=PEDREIRO, qtd=2)], MAPA)
    assert total == 2
    assert json.loads(js) == [{"funcao_id": str(PEDREIRO), "nome": "Pedreiro", "qtd": 2}]


def test_soma_e_total():
    itens = [EfetivoItem(funcao_id=PEDREIRO, qtd=2), EfetivoItem(funcao_id=SERVENTE, qtd=3)]
    js, total = consolidar_efetivo(itens, MAPA)
    assert total == 5
    assert [i["nome"] for i in json.loads(js)] == ["Pedreiro", "Servente"]


def test_dedupe_soma_qtd_preserva_ordem():
    itens = [
        EfetivoItem(funcao_id=SERVENTE, qtd=1),
        EfetivoItem(funcao_id=PEDREIRO, qtd=2),
        EfetivoItem(funcao_id=SERVENTE, qtd=4),  # duplicado → soma na 1ª aparição
    ]
    js, total = consolidar_efetivo(itens, MAPA)
    arr = json.loads(js)
    assert total == 7
    assert arr == [
        {"funcao_id": str(SERVENTE), "nome": "Servente", "qtd": 5},
        {"funcao_id": str(PEDREIRO), "nome": "Pedreiro", "qtd": 2},
    ]


def test_funcao_fora_do_mapa_404():
    with pytest.raises(HTTPException) as ei:
        consolidar_efetivo([EfetivoItem(funcao_id=uuid.uuid4(), qtd=1)], MAPA)
    assert ei.value.status_code == 404


def test_nome_canonico_ignora_renomeacao_local():
    # o EfetivoItem nem aceita `nome`; o gravado vem SEMPRE do mapa (biblioteca = fonte da verdade).
    js, _ = consolidar_efetivo([EfetivoItem(funcao_id=MESTRE, qtd=1)], MAPA)
    assert json.loads(js)[0]["nome"] == "Mestre de obras"
