"""Testes do motor de lembretes: regras PURAS (sem banco) + degradação do humanizador (sem rede)."""

from app.core.config import get_settings
from app.services import lembretes
from app.services.ollama_client import humanizar_item


def _linha(**kw):
    base = {
        "id": "00000000-0000-0000-0000-000000000001",
        "nome": "Cliente X",
        "etapa": "lead",
        "obra_id": None,
        "contato_telefone": "11999",
        "contato_email": None,
        "valor_estimado": None,
        "proximo_followup": None,
        "seq_humano": 1,
        "tem_comentario": False,
        "dias_followup": None,
        "dias_sem_toque": 0,
        "dias_desde_update": 0,
    }
    base.update(kw)
    return base


def test_followup_vencido_e_alta():
    cfg = get_settings()
    aps = lembretes._avaliar([_linha(etapa="contato", dias_followup=3)], cfg)
    assert len(aps) == 1
    assert aps[0]["regra_id"] == "R1"
    assert aps[0]["severidade"] == "alta"
    assert aps[0]["dias"] == 3


def test_dedup_uma_por_oportunidade_maior_severidade():
    cfg = get_settings()
    # bate R1 (alta, follow-up vencido) e R7 (baixa, sem canal) ao mesmo tempo → fica só a alta.
    linha = _linha(etapa="contato", dias_followup=5, contato_telefone=None, contato_email=None)
    aps = lembretes._avaliar([linha], cfg)
    assert len(aps) == 1
    assert aps[0]["severidade"] == "alta"


def test_ganho_sem_obra_gera_r8():
    cfg = get_settings()
    aps = lembretes._avaliar([_linha(etapa="ganho", obra_id=None, dias_desde_update=5)], cfg)
    assert aps and aps[0]["regra_id"] == "R8"


def test_ganho_com_obra_nao_gera_nada():
    cfg = get_settings()
    linha = _linha(
        etapa="ganho", obra_id="x", dias_desde_update=50, contato_telefone=None, contato_email=None
    )
    assert lembretes._avaliar([linha], cfg) == []


def test_ordena_alta_antes_de_media():
    cfg = get_settings()
    linhas = [
        _linha(id="a", etapa="contato", dias_sem_toque=cfg.LEMBRETES_DIAS_ESFRIANDO),  # R3 média
        _linha(id="b", etapa="contato", dias_followup=10),  # R1 alta
    ]
    aps = lembretes._ordena(lembretes._avaliar(linhas, cfg))
    assert aps[0]["severidade"] == "alta"


async def test_humanizar_noop_com_flag_off():
    # LEMBRETES_LLM_ENABLED nasce False → humanizador retorna None sem tocar a rede.
    fato = {
        "titulo": "x", "nome": "y", "etapa": "lead", "dias": 1,
        "categoria": "c", "severidade": "alta", "mensagem": "m",
    }
    assert await humanizar_item(fato) is None
