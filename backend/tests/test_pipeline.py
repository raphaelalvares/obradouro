"""Pipeline do projeto (0097) — testes PUROS (sem banco).

Cobre os rótulos/ordem das 9 etapas fixas, a derivação de `acao_pendente`/`gate` por etapa e a
validação dos schemas. RPC/RLS/guard (garantir_etapas_projeto, decidir_iniciar_obra, pipeline_gates)
são integração com DB — fora do pytest puro, como no 0088.
"""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.pipeline import (
    EtapaAnexoOut,
    EtapaLinkCreate,
    EtapaProjetoOut,
    EtapaUpdate,
    IniciarObraDecisao,
    PipelineOut,
)
from app.services.pipeline import _ETAPAS, GATES, ORDEM, ROTULOS, _acao_pendente, _monta


# ============================ metadados das 9 etapas ============================
def test_nove_etapas_fixas_em_ordem():
    codigos = [c for c, _, _ in _ETAPAS]
    assert codigos == [
        "medicao", "base", "layouts", "projeto_3d", "apresentacao",
        "aprovacao", "manual", "orcamento", "iniciar_obra",
    ]
    assert ORDEM["medicao"] == 1 and ORDEM["iniciar_obra"] == 9


def test_rotulos_e_gates():
    assert ROTULOS["iniciar_obra"] == "Início da obra"
    assert ROTULOS["orcamento"] == "Orçamento da obra (EVF)"
    # os 3 gates ligam pros fluxos existentes
    assert GATES["layouts"] == "revisao"
    assert GATES["aprovacao"] == "revisao"
    assert GATES["orcamento"] == "proposta"
    assert GATES["iniciar_obra"] == "iniciar_obra"
    assert GATES["medicao"] is None


# ============================ acao_pendente (estado vivo dos gates) ============================
def test_acao_pendente_revisao():
    assert _acao_pendente("layouts", {}, {"rev_pendente": True}) is True
    assert _acao_pendente("layouts", {}, {"rev_pendente": False}) is False


def test_acao_pendente_proposta():
    assert _acao_pendente("orcamento", {}, {"orc_pendente": True}) is True
    assert _acao_pendente("orcamento", {}, {"orc_pendente": False}) is False


def test_acao_pendente_iniciar_obra_depende_de_aprovacao_e_decisao():
    # só pende quando o orçamento foi aprovado E ainda não há decisão
    assert _acao_pendente("iniciar_obra", {"decisao": None}, {"orc_aprovado": True}) is True
    # já decidiu → não pende
    assert _acao_pendente("iniciar_obra", {"decisao": "sim"}, {"orc_aprovado": True}) is False
    # orçamento não aprovado → ainda não é a vez do cliente
    assert _acao_pendente("iniciar_obra", {"decisao": None}, {"orc_aprovado": False}) is False


def test_acao_pendente_etapa_sem_gate():
    assert _acao_pendente("base", {}, {"rev_pendente": True, "orc_pendente": True}) is False


# ============================ _monta (linha → shape de saída) ============================
def test_monta_etapa_valida_schema():
    out = _monta({"etapa": "medicao", "ordem": 1, "status": "a_fazer"}, {})
    assert out["rotulo"] == "Agendamento de medição"
    assert out["gate"] is None
    assert out["acao_pendente"] is False
    EtapaProjetoOut(**out)  # bate com o schema


def test_monta_default_status_quando_ausente():
    out = _monta({"etapa": "layouts"}, {"rev_pendente": True})
    assert out["status"] == "a_fazer"
    assert out["gate"] == "revisao"
    assert out["acao_pendente"] is True
    EtapaProjetoOut(**out)


# ============================ schemas (poka-yoke) ============================
def test_iniciar_obra_decisao_so_sim_ou_nao():
    assert IniciarObraDecisao(decisao="sim").decisao == "sim"
    assert IniciarObraDecisao(decisao="nao").decisao == "nao"
    with pytest.raises(ValidationError):
        IniciarObraDecisao(decisao="talvez")


def test_etapa_update_tudo_opcional():
    u = EtapaUpdate()
    assert u.status is None and u.data_prevista is None and u.observacao is None


def test_etapa_update_status_invalido():
    with pytest.raises(ValidationError):
        EtapaUpdate(status="qualquer")


def test_pipeline_out_default_vazio():
    p = PipelineOut()
    assert p.etapas == [] and p.etapa_atual is None


# ============================ material da etapa (arquivo|link, 0099) ============================
def test_monta_inclui_anexos():
    anexos = [
        {
            "id": uuid.uuid4(),
            "etapa": "apresentacao",
            "tipo": "link",
            "label": "Canva",
            "url": "https://canva.com/x",
            "is_pdf": False,
            "tem_thumb": False,
            "ordem": 0,
            "created_at": "2026-06-30T12:00:00Z",
        }
    ]
    out = _monta({"etapa": "apresentacao", "status": "em_andamento"}, {}, anexos)
    assert out["anexos"] == anexos
    EtapaProjetoOut(**out)  # bate com o schema (anexos vira list[EtapaAnexoOut])


def test_monta_sem_anexos_default_vazio():
    out = _monta({"etapa": "base", "status": "a_fazer"}, {})
    assert out["anexos"] == []
    EtapaProjetoOut(**out)


def test_etapa_link_create_exige_http():
    ok = EtapaLinkCreate(id=uuid.uuid4(), url="https://sketchfab.com/abc", label="Tour 3D")
    assert ok.url == "https://sketchfab.com/abc"
    # http também vale; espaços são aparados
    assert EtapaLinkCreate(id=uuid.uuid4(), url="  http://x.com  ").url == "http://x.com"
    with pytest.raises(ValidationError):
        EtapaLinkCreate(id=uuid.uuid4(), url="ftp://x.com")
    with pytest.raises(ValidationError):
        EtapaLinkCreate(id=uuid.uuid4(), url="sketchfab.com/abc")


def test_etapa_anexo_out_arquivo_e_link():
    arq = EtapaAnexoOut(
        id=uuid.uuid4(),
        etapa="apresentacao",
        tipo="arquivo",
        nome_arquivo="proposta.pdf",
        content_type="application/pdf",
        is_pdf=True,
        created_at="2026-06-30T12:00:00Z",
    )
    assert arq.tipo == "arquivo" and arq.is_pdf is True
    lnk = EtapaAnexoOut(
        id=uuid.uuid4(),
        etapa="projeto_3d",
        tipo="link",
        url="https://x.com",
        created_at="2026-06-30T12:00:00Z",
    )
    assert lnk.tipo == "link" and lnk.url == "https://x.com"
