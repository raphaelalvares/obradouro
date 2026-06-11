"""Testes de Equipes (Fatia A · parte 2) — validação do contrato (sem banco).

Foco: a cor é hex #RRGGBB (poka-yoke p/ o Gantt ficar legível) e o nome não pode ser só-espaços.
O CRUD em si é DB-bound (RLS self); a regra pura testável aqui é a dos validadores do schema.
"""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.equipes import _COR_PADRAO, EquipeCreate, EquipeUpdate


def test_create_normaliza_nome_e_aceita_cor_valida():
    eq = EquipeCreate(id=uuid.uuid4(), nome="  Elétrica - João  ", cor="#5b8def")
    assert eq.nome == "Elétrica - João"  # trim
    assert eq.cor == "#5B8DEF"  # normaliza p/ maiúsculo


def test_create_cor_padrao_quando_omitida():
    eq = EquipeCreate(id=uuid.uuid4(), nome="Hidráulica")
    assert eq.cor == _COR_PADRAO


def test_create_rejeita_nome_so_espacos():
    with pytest.raises(ValidationError):
        EquipeCreate(id=uuid.uuid4(), nome="   ")


@pytest.mark.parametrize("cor", ["azul", "#FFF", "#12345", "#1234567", "123456", "#GGGGGG"])
def test_create_rejeita_cor_invalida(cor):
    with pytest.raises(ValidationError):
        EquipeCreate(id=uuid.uuid4(), nome="Pintura", cor=cor)


def test_update_parcial_valida_cor_quando_presente():
    upd = EquipeUpdate(cor="#abcdef")
    assert upd.cor == "#ABCDEF"
    with pytest.raises(ValidationError):
        EquipeUpdate(cor="roxo")
    # campos omitidos seguem None (exclude_unset no service decide o que gravar)
    assert EquipeUpdate(ativo=False).nome is None
