"""Testes PUROS do pool de armazenamento do admin (sem DB/rede):
  • resumo_armazenamento: agregação físico vs cotas, override, ilimitado, overcommit.
  • _bytes_do_arquivo: quotaBytesUsed é a fonte correta (não 'size') — a correção do cálculo Drive.
"""

from app.services.admin import resumo_armazenamento
from app.services.storage.drive import _bytes_do_arquivo

_MB = 1024 * 1024
_GB = 1024 * _MB


def _tenant(bytes_usados: int, limite_mb: int, plano: str = "pro") -> dict:
    return {
        "armazenamento_bytes": bytes_usados,
        "armazenamento_limite_mb": limite_mb,
        "plano_codigo": plano,
    }


def test_resumo_soma_consumo_e_comprometido():
    tenants = [
        _tenant(100 * _MB, 5120, "alicerce"),  # 5 GB
        _tenant(2 * _GB, 51200, "pro"),  # 50 GB
        _tenant(10 * _MB, 500, "free"),  # 500 MB
    ]
    conta = {
        "total_bytes": 5 * 1024 * _GB,  # 5 TB
        "usado_bytes": 3 * _GB,
        "usado_drive_bytes": 2 * _GB,
        "lixeira_bytes": 0,
    }
    r = resumo_armazenamento(tenants, conta, "drive")
    assert r["consumo_contabilizado_bytes"] == 100 * _MB + 2 * _GB + 10 * _MB
    assert r["comprometido_mb"] == 5120 + 51200 + 500
    assert r["comprometido_pagantes_mb"] == 5120 + 51200  # free fora
    assert r["n_clientes"] == 3
    assert r["total_bytes"] == 5 * 1024 * _GB
    assert r["usado_real_bytes"] == 3 * _GB
    assert r["ilimitado_presente"] is False
    assert r["overcommit"] is False
    # livre p/ alocar = total − comprometido
    assert r["livre_para_alocar_bytes"] == 5 * 1024 * _GB - (5120 + 51200 + 500) * _MB


def test_resumo_override_de_pool_tem_prioridade():
    # STORAGE_POOL_MB reserva folga: o total vem do override, não do about da conta.
    r = resumo_armazenamento([_tenant(0, 500, "free")], {"total_bytes": 5 * 1024 * _GB}, "drive",
                             pool_override_mb=1024)  # 1 GB só
    assert r["total_bytes"] == 1024 * _MB


def test_resumo_ilimitado_nao_entra_na_soma():
    tenants = [_tenant(0, -1, "pro"), _tenant(0, 5120, "alicerce")]
    r = resumo_armazenamento(tenants, None, "drive")
    assert r["ilimitado_presente"] is True
    assert r["comprometido_mb"] == 5120  # -1 (ilimitado) não soma


def test_resumo_overcommit_quando_promete_mais_que_o_fisico():
    tenants = [_tenant(0, 51200, "pro")]  # 50 GB comprometidos
    r = resumo_armazenamento(tenants, {"total_bytes": 10 * _GB}, "drive")  # só 10 GB físicos
    assert r["overcommit"] is True
    assert r["livre_para_alocar_bytes"] == 10 * _GB - 51200 * _MB  # negativo (informativo)


def test_resumo_sem_conta_deixa_fisico_none():
    r = resumo_armazenamento([_tenant(0, 500, "free")], None, "local")
    assert r["conta_disponivel"] is False
    assert r["total_bytes"] is None
    assert r["usado_real_bytes"] is None
    assert r["livre_para_alocar_bytes"] is None
    assert r["overcommit"] is False


def test_resumo_pool_vazio():
    r = resumo_armazenamento([], None, "local")
    assert r["consumo_contabilizado_bytes"] == 0
    assert r["comprometido_mb"] == 0
    assert r["n_clientes"] == 0


def test_bytes_do_arquivo_prefere_quota_bytes_used():
    # quotaBytesUsed (o que pesa na cota) manda, mesmo diferente de size.
    assert _bytes_do_arquivo({"quotaBytesUsed": "1500", "size": "1000"}) == 1500


def test_bytes_do_arquivo_cai_no_size_quando_sem_quota():
    assert _bytes_do_arquivo({"size": "2048"}) == 2048


def test_bytes_do_arquivo_zero_quando_sem_nenhum():
    assert _bytes_do_arquivo({"id": "x", "mimeType": "image/jpeg"}) == 0
