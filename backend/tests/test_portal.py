"""Portal do Cliente (0089/0096) — testes PUROS (sem banco).

Cobre a validação dos schemas (e-mail; PRAZO de validade; contexto de roteamento) e o helper
`_acesso_out` (status `cadastrado` derivado de `profile_id`; `expirado` derivado de `expira_em`). A
reconciliação/guard/RPC e a expiração no RLS são integração com DB — fora do pytest puro (ver 0088).
"""

import datetime as dt
import types
import uuid

import pytest
from pydantic import ValidationError

from app.schemas.portal import (
    AcessoClienteCreate,
    AcessoClienteOut,
    AcessoPrazo,
    PortalContextoOut,
)
from app.services.portal import _acesso_out


def _fake_row(profile_id=None, *, validade_tipo="sem_prazo", validade_ate=None, expira_em=None):
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        email="cliente@email.com",
        estado="ativo" if profile_id else "pendente",
        profile_id=profile_id,
        validade_tipo=validade_tipo,
        validade_ate=validade_ate,
        expira_em=expira_em,
        projeto_id=uuid.uuid4(),
        obra_id=None,
        created_at=dt.datetime(2026, 6, 26, 12, 0, 0),
    )


# ============================ _acesso_out (status legível) ============================
def test_acesso_out_pendente_nao_cadastrado():
    out = _acesso_out(_fake_row(profile_id=None))
    assert out["cadastrado"] is False
    assert out["estado"] == "pendente"
    assert out["expirado"] is False  # sem_prazo nunca expira
    AcessoClienteOut(**out)  # o shape bate com o schema de saída


def test_acesso_out_vinculado_cadastrado():
    out = _acesso_out(_fake_row(profile_id=uuid.uuid4()))
    assert out["cadastrado"] is True
    AcessoClienteOut(**out)


def test_acesso_out_expirado_quando_passou():
    passado = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    out = _acesso_out(_fake_row(validade_tipo="data", expira_em=passado))
    assert out["expirado"] is True


def test_acesso_out_nao_expirado_no_futuro():
    futuro = dt.datetime.now(dt.UTC) + dt.timedelta(days=1)
    out = _acesso_out(_fake_row(validade_tipo="data", expira_em=futuro))
    assert out["expirado"] is False


# ============================ AcessoPrazo (poka-yoke do prazo) ============================
def test_prazo_data_exige_validade_ate():
    with pytest.raises(ValidationError):
        AcessoPrazo(validade_tipo="data", validade_ate=None)


def test_prazo_data_rejeita_passado():
    ontem = dt.date.today() - dt.timedelta(days=1)
    with pytest.raises(ValidationError):
        AcessoPrazo(validade_tipo="data", validade_ate=ontem)


def test_prazo_data_aceita_futuro():
    amanha = dt.date.today() + dt.timedelta(days=1)
    p = AcessoPrazo(validade_tipo="data", validade_ate=amanha)
    assert p.validade_ate == amanha


def test_prazo_sem_prazo_zera_data():
    # mesmo passando uma data, 'sem_prazo'/'entrega' a descartam (poka-yoke)
    p = AcessoPrazo(validade_tipo="sem_prazo", validade_ate=dt.date.today())
    assert p.validade_ate is None


def test_prazo_entrega_zera_data():
    p = AcessoPrazo(validade_tipo="entrega", validade_ate=dt.date.today())
    assert p.validade_ate is None


def test_prazo_tipo_invalido():
    with pytest.raises(ValidationError):
        AcessoPrazo(validade_tipo="qualquer")


# ============================ schemas (poka-yoke do acesso) ============================
def test_create_aceita_email_valido_com_prazo():
    amanha = dt.date.today() + dt.timedelta(days=1)
    ac = AcessoClienteCreate(email="cliente@email.com", validade_tipo="data", validade_ate=amanha)
    assert ac.email == "cliente@email.com"
    assert ac.validade_tipo == "data"


def test_create_default_sem_prazo():
    ac = AcessoClienteCreate(email="cliente@email.com")
    assert ac.validade_tipo == "sem_prazo"
    assert ac.validade_ate is None


def test_create_rejeita_email_invalido():
    with pytest.raises(ValidationError):
        AcessoClienteCreate(email="não-é-email")


def test_contexto_default_vazio():
    ctx = PortalContextoOut(eh_arquiteto=True, eh_cliente=False)
    assert ctx.projetos == []
    assert ctx.obras == []
    assert ctx.tem_papel_cliente is False


def test_contexto_cliente_com_projeto_e_obra():
    ctx = PortalContextoOut(
        eh_arquiteto=False,
        eh_cliente=True,
        tem_papel_cliente=True,
        projetos=[{"id": uuid.uuid4(), "nome": "Reforma 302", "seq_humano": 7, "obra_id": None}],
        obras=[{"id": uuid.uuid4(), "nome": "Obra 302", "seq_humano": 3, "status": "ativa"}],
    )
    assert ctx.eh_cliente is True
    assert ctx.projetos[0].nome == "Reforma 302"
    assert ctx.obras[0].status == "ativa"
