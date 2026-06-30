"""Testes do assistente: snapshot puro (sem banco) + degradação sem Ollama."""

from app.core.config import get_settings
from app.services import assistente
from app.services.ollama_client import conversar


def _op(**kw):
    base = {
        "id": "00000000-0000-0000-0000-000000000001",
        "nome": "Casa Raphael",
        "etapa": "visita",
        "contato_nome": "Raphael",
        "valor_estimado": 500000,
        "proximo_followup": "2026-06-10",
        "seq_humano": 1,
    }
    base.update(kw)
    return base


def _apont(**kw):
    base = {
        "severidade": "alta",
        "nome": "Casa Raphael",
        "seq_humano": 1,
        "mensagem": "Follow-up atrasado há 14 dia(s).",
    }
    base.update(kw)
    return base


def test_snapshot_inclui_funil_pendencia_e_oportunidade():
    cfg = get_settings()
    txt = assistente._montar_snapshot([_op()], [_apont()], cfg)
    assert "em negociação" in txt
    assert "Pendências (1)" in txt
    assert "Casa Raphael" in txt
    assert "Follow-up atrasado há 14" in txt


def test_snapshot_sem_pendencia():
    cfg = get_settings()
    txt = assistente._montar_snapshot([_op()], [], cfg)
    assert "(nada pendente)" in txt


def test_fallback_lista_pendencias():
    txt = assistente._fallback([_apont()])
    assert "indisponível" in txt
    assert "Casa Raphael" in txt


async def test_assistente_degrada_sem_ollama():
    # ASSISTENTE_ENABLED nasce False → conversar retorna None sem tocar a rede.
    assert await conversar([{"role": "user", "content": "oi"}]) is None
