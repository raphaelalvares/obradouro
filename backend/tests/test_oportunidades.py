"""Comercial — dois funis (Projeto + Obra) na oportunidade (0088).

Sem banco: cobre a decisão PURA do auto-abrir do funil de obra ao ganhar o projeto e a validação dos
schemas (etapa opcional p/ lead só-obra; etapa_obra; valor_obra). O sync via orçamento/guard/RPC é
de integração (depende de DB) — fora do pytest puro atual.
"""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.oportunidades import OportunidadeCreate, OportunidadeUpdate
from app.services.oportunidades import aplicar_auto_abrir_obra


# ============================ auto-abrir funil de obra (pura) ============================
def test_ganhar_projeto_abre_obra_quando_fora_dela():
    out = aplicar_auto_abrir_obra({"etapa": "ganho"}, None)
    assert out == {"etapa": "ganho", "etapa_obra": "a_orcar"}


def test_ganhar_projeto_nao_recua_quem_ja_esta_em_obra():
    # já está em 'orcamento' → não sobrescreve (forward-only).
    out = aplicar_auto_abrir_obra({"etapa": "ganho"}, "orcamento")
    assert out == {"etapa": "ganho"}


def test_ganhar_projeto_nao_mexe_se_terminal_de_obra():
    out = aplicar_auto_abrir_obra({"etapa": "ganho"}, "ganho")
    assert out == {"etapa": "ganho"}


def test_etapa_obra_explicita_no_patch_tem_prioridade():
    # se o PATCH já traz etapa_obra, respeita (não força 'a_orcar').
    fields = {"etapa": "ganho", "etapa_obra": "apresentado"}
    assert aplicar_auto_abrir_obra(fields, None) == fields


def test_outras_etapas_nao_abrem_obra():
    assert aplicar_auto_abrir_obra({"etapa": "contato"}, None) == {"etapa": "contato"}
    assert aplicar_auto_abrir_obra({"valor_estimado": 10}, None) == {"valor_estimado": 10}


# ============================ schemas (poka-yoke dos dois funis) ============================
def test_create_default_projeto():
    op = OportunidadeCreate(id=uuid.uuid4(), nome="Lead")
    assert op.etapa == "lead"
    assert op.etapa_obra is None
    assert op.valor_obra is None


def test_create_so_obra_etapa_nula():
    op = OportunidadeCreate(id=uuid.uuid4(), nome="Só obra", etapa=None, etapa_obra="a_orcar")
    assert op.etapa is None
    assert op.etapa_obra == "a_orcar"


def test_create_ambos_com_valores():
    op = OportunidadeCreate(
        id=uuid.uuid4(), nome="Ambos", etapa="lead", etapa_obra="a_orcar",
        valor_estimado=5000, valor_obra=120000,
    )
    assert op.valor_estimado == 5000
    assert op.valor_obra == 120000


def test_etapa_obra_invalida_rejeitada():
    # 'visita' é etapa só do funil de projeto — inválida no funil de obra.
    with pytest.raises(ValidationError):
        OportunidadeCreate(id=uuid.uuid4(), nome="X", etapa_obra="visita")


def test_update_aceita_campos_dos_dois_funis():
    upd = OportunidadeUpdate(etapa_obra="apresentado", valor_obra=200000)
    dump = upd.model_dump(exclude_unset=True)
    assert dump == {"etapa_obra": "apresentado", "valor_obra": 200000}
