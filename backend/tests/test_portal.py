"""Portal do Cliente (0089) — testes PUROS (sem banco).

Cobre a validação dos schemas (e-mail do acesso; contexto de roteamento) e o helper `_acesso_out`
(status `cadastrado` derivado de `profile_id`). A reconciliação/guard/RPC (a `reconciliar_acessos_*`
e a `vincular_cliente_na_obra`) são integração com DB — fora do pytest puro atual, como no 0088.
"""

import datetime as dt
import types
import uuid

import pytest
from pydantic import ValidationError

from app.schemas.portal import AcessoClienteCreate, AcessoClienteOut, PortalContextoOut
from app.services.portal import _acesso_out


def _fake_row(profile_id):
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        email="cliente@email.com",
        estado="ativo" if profile_id else "pendente",
        profile_id=profile_id,
        projeto_id=uuid.uuid4(),
        obra_id=None,
        created_at=dt.datetime(2026, 6, 26, 12, 0, 0),
    )


# ============================ _acesso_out (status legível) ============================
def test_acesso_out_pendente_nao_cadastrado():
    out = _acesso_out(_fake_row(profile_id=None))
    assert out["cadastrado"] is False
    assert out["estado"] == "pendente"
    # o shape bate com o schema de saída
    AcessoClienteOut(**out)


def test_acesso_out_vinculado_cadastrado():
    out = _acesso_out(_fake_row(profile_id=uuid.uuid4()))
    assert out["cadastrado"] is True
    AcessoClienteOut(**out)


# ============================ schemas (poka-yoke do acesso) ============================
def test_create_aceita_email_valido():
    ac = AcessoClienteCreate(email="cliente@email.com")
    assert ac.email == "cliente@email.com"


def test_create_rejeita_email_invalido():
    with pytest.raises(ValidationError):
        AcessoClienteCreate(email="não-é-email")


def test_contexto_default_vazio():
    ctx = PortalContextoOut(eh_arquiteto=True, eh_cliente=False)
    assert ctx.projetos == []
    assert ctx.obras == []


def test_contexto_cliente_com_projeto_e_obra():
    ctx = PortalContextoOut(
        eh_arquiteto=False,
        eh_cliente=True,
        projetos=[{"id": uuid.uuid4(), "nome": "Reforma 302", "seq_humano": 7, "obra_id": None}],
        obras=[{"id": uuid.uuid4(), "nome": "Obra 302", "seq_humano": 3, "status": "ativa"}],
    )
    assert ctx.eh_cliente is True
    assert ctx.projetos[0].nome == "Reforma 302"
    assert ctx.obras[0].status == "ativa"
