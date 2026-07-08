"""Endurecimento (padrão OURO): rate limiter, validadores de CORS e escopo explícito anti-IDOR.

Tudo unitário/estático (sem DB) — casa com o estilo do resto da suíte (conftest só seta env).
"""

import inspect

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.ratelimit import SlidingWindowLimiter
from app.services import checklist, oportunidades


# ------------------------------------------------------------------ rate limiter
def test_limiter_libera_ate_o_teto_depois_bloqueia():
    lim = SlidingWindowLimiter()
    for i in range(3):
        assert lim.hit("k", limit=3, window_s=60, now=1000.0 + i).allowed
    d = lim.hit("k", limit=3, window_s=60, now=1003.0)
    assert d.allowed is False
    assert d.retry_after >= 1  # informa quando tentar de novo


def test_limiter_janela_desliza_e_libera_depois():
    lim = SlidingWindowLimiter()
    for _ in range(3):
        lim.hit("k", limit=3, window_s=60, now=1000.0)
    assert lim.hit("k", limit=3, window_s=60, now=1000.0).allowed is False  # cheio na janela
    assert lim.hit("k", limit=3, window_s=60, now=1061.0).allowed is True  # janela passou → libera


def test_limiter_chaves_independentes():
    lim = SlidingWindowLimiter()
    for _ in range(3):
        assert lim.hit("ip:a", limit=3, window_s=60, now=1.0).allowed
    # outra chave (outro IP/email) não é afetada pelo estouro da primeira
    assert lim.hit("ip:b", limit=3, window_s=60, now=1.0).allowed is True


def test_limiter_teto_duro_de_chaves_despeja_lru():
    lim = SlidingWindowLimiter()
    lim._MAX_KEYS = 3  # instância sombreia o atributo de classe
    for i in range(3):
        lim.hit(f"k{i}", limit=5, window_s=60, now=1000.0 + i)  # 3 chaves ativas
    lim.hit("k3", limit=5, window_s=60, now=1003.0)  # 4ª: nenhuma expirou → despeja a LRU
    assert len(lim._hits) == 3  # teto DURO respeitado
    assert "k3" in lim._hits and "k0" not in lim._hits  # a menos-recente (k0) saiu


# ------------------------------------------------------------------ CORS: fail-closed
def test_cors_origins_wildcard_e_rejeitado():
    with pytest.raises(ValidationError):
        Settings(CORS_ORIGINS="*")


def test_cors_origins_wildcard_no_meio_da_lista_e_rejeitado():
    with pytest.raises(ValidationError):
        Settings(CORS_ORIGINS="https://obradouro.com.br,*")


def test_cors_regex_deve_ser_ancorado():
    with pytest.raises(ValidationError):
        Settings(CORS_ORIGINS="https://x.com", CORS_ORIGIN_REGEX="https://obradouro-.*.vercel.app")
    # ancorado (^...$) passa
    ok = Settings(CORS_ORIGINS="https://x.com", CORS_ORIGIN_REGEX=r"^https://x\.vercel\.app$")
    assert ok.CORS_ORIGIN_REGEX == r"^https://x\.vercel\.app$"


# ------------------------------------------------------------ IDOR: escopo explícito (1ª camada)
def test_oportunidades_leituras_filtram_pelo_dono():
    assert oportunidades._OWNER == "tenant_id = (select auth.uid())"
    for sql in (oportunidades._SQL_GET, oportunidades._SQL_LIST, oportunidades._SQL_EXISTS):
        assert oportunidades._OWNER in sql


def test_checklist_idempotencia_escopada_por_obra():
    # o SELECT de idempotência de cada create (e o merge) filtra por obra — não confia só na RLS.
    for fn in (
        checklist.create_etapa,
        checklist._merge_existing_etapa,
        checklist.create_subetapa,
        checklist._merge_existing_subetapa,
        checklist.create_item,
        checklist._merge_existing_item,
    ):
        assert "obra_id = cast(:o as uuid)" in inspect.getsource(fn), fn.__name__
