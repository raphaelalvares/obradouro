"""Testes do 'virar obra' (sem banco): payload do orçamento → RPC importar_checklist."""

from app.services.orcamento_obra import _payload_do_orcamento


def _item(**kw) -> dict:
    base = {
        "etapa": "Pintura", "ordem_etapa": 1, "descricao": "Parede", "ordem": 1,
        "ambiente": None, "unidade": "m²", "quantidade": 10,
        "valor_mo": 20, "valor_material": 5, "valor_equipamento": 0,
    }
    base.update(kw)
    return base


def test_payload_agrupa_etapas_estrutura_sem_custo():
    # semeia só a ESTRUTURA (nome/cômodo/unidade/qtd) — NUNCA custos (não vazar margem ao cliente).
    payload = _payload_do_orcamento(
        [
            _item(valor_equipamento=2),
            _item(etapa="Elétrica", ordem_etapa=2, descricao="Tomadas", quantidade=None,
                  valor_mo=300, valor_material=100, valor_equipamento=0),
        ]
    )
    assert [e["nome"] for e in payload] == ["Pintura", "Elétrica"]
    p = payload[0]["itens"][0]
    assert set(p) == {"nome", "nome_norm", "ordem", "ambiente", "unidade", "quantidade"}
    assert "custo_mao_obra" not in p and "custo_material" not in p and "custo_total" not in p
    assert p["quantidade"] == 10.0
    assert p["unidade"] == "m²"
    assert payload[1]["itens"][0]["quantidade"] is None  # verba preserva qtd nula


def test_payload_etapa_repetida_usa_menor_ordem():
    payload = _payload_do_orcamento(
        [
            _item(ordem_etapa=5, descricao="a"),
            _item(ordem_etapa=2, descricao="b"),
            _item(etapa="Outra", ordem_etapa=3, descricao="c"),
        ]
    )
    assert [(e["nome"], e["ordem"]) for e in payload] == [("Pintura", 2), ("Outra", 3)]
    assert [i["nome"] for i in payload[0]["itens"]] == ["a", "b"]


def test_payload_mesmo_servico_em_comodos_diferentes_desambigua():
    # dedupe do checklist é (etapa, nome_norm): sem o sufixo, o 2º cômodo sumiria.
    payload = _payload_do_orcamento(
        [
            _item(ambiente="Cozinha"),
            _item(ambiente="Banheiro"),
        ]
    )
    nomes = [i["nome"] for i in payload[0]["itens"]]
    assert nomes == ["Parede (Cozinha)", "Parede (Banheiro)"]


def test_payload_duplicata_real_e_descartada():
    # mesmo nome SEM cômodo p/ desambiguar → 2ª some (a RPC pularia do mesmo jeito).
    payload = _payload_do_orcamento([_item(), _item(valor_mo=99)])
    assert len(payload[0]["itens"]) == 1


def test_payload_ordem_dos_itens_e_sequencial():
    payload = _payload_do_orcamento([_item(descricao="a"), _item(descricao="b")])
    assert [i["ordem"] for i in payload[0]["itens"]] == [1, 2]
