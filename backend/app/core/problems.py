"""Erros de limite (soft-limit) como problem+json (RFC 9457), para o front mostrar o upsell.

As funções SQL levantam P0001 com a mensagem parseável 'limite_obras_ativas:<lim>:<atual>'
(P0001/raise_exception é genérico demais para distinguir por sqlstate). Aqui traduzimos isso
numa resposta 403 application/problem+json com os dados do CTA de upgrade.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

CRIA_PROBLEM_BASE = "https://cria.app/problems/"
_MARKER = "limite_obras_ativas:"
_MARKER_ARMAZ = "limite_armazenamento:"


class LimiteAtivasError(Exception):
    """Limite de obras ativas atingido (soft-limit → upsell)."""

    def __init__(self, limite: int, atual: int):
        self.limite = limite
        self.atual = atual


class LimiteArmazenamentoError(Exception):
    """Quota de armazenamento atingida (soft-limit → upsell)."""

    def __init__(self, limite_mb: int, usado_bytes: int):
        self.limite_mb = limite_mb
        self.usado_bytes = usado_bytes


def limite_from_exc(exc: Exception) -> LimiteAtivasError | None:
    """Reconhece o P0001 'limite_obras_ativas:<lim>:<atual>'. Retorna None se for outro erro."""
    msg = str(getattr(exc, "orig", exc))
    if _MARKER not in msg:
        return None
    frag = msg.split(_MARKER, 1)[1]
    parts = frag.replace("\n", " ").split(":")
    try:
        limite = int(parts[0])
        atual = int(parts[1].split()[0])
    except (IndexError, ValueError):
        return LimiteAtivasError(0, 0)
    return LimiteAtivasError(limite, atual)


def limite_armazenamento_from_exc(exc: Exception) -> LimiteArmazenamentoError | None:
    """Reconhece o P0001 'limite_armazenamento:<lim_mb>:<usado_bytes>'. None se for outro erro."""
    msg = str(getattr(exc, "orig", exc))
    if _MARKER_ARMAZ not in msg:
        return None
    frag = msg.split(_MARKER_ARMAZ, 1)[1]
    parts = frag.replace("\n", " ").split(":")
    try:
        limite_mb = int(parts[0])
        usado = int(parts[1].split()[0])
    except (IndexError, ValueError):
        return LimiteArmazenamentoError(0, 0)
    return LimiteArmazenamentoError(limite_mb, usado)


async def limite_ativas_handler(_: Request, exc: LimiteAtivasError) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        media_type="application/problem+json",
        content={
            "type": CRIA_PROBLEM_BASE + "limite-obras-ativas",
            "title": "Limite de obras ativas atingido",
            "status": 403,
            "detail": f"Seu plano permite {exc.limite} obra(s) ativa(s); você já tem {exc.atual}.",
            "eixo": "obras_ativas",
            "limite": exc.limite,
            "atual": exc.atual,
            "upgrade_cta": True,
        },
    )


async def limite_armazenamento_handler(_: Request, exc: LimiteArmazenamentoError) -> JSONResponse:
    usado_mb = round(exc.usado_bytes / (1024 * 1024), 1)
    return JSONResponse(
        status_code=403,
        media_type="application/problem+json",
        content={
            "type": CRIA_PROBLEM_BASE + "limite-armazenamento",
            "title": "Armazenamento esgotado",
            "status": 403,
            "detail": f"Seu plano inclui {exc.limite_mb} MB; você já usou {usado_mb} MB.",
            "eixo": "armazenamento",
            "limite_mb": exc.limite_mb,
            "usado_bytes": exc.usado_bytes,
            "upgrade_cta": True,
        },
    )
