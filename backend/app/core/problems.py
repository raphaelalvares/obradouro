"""Erros de limite (soft-limit) como problem+json (RFC 9457), para o front mostrar o upsell.

As funções SQL levantam P0001 com a mensagem parseável 'limite_obras_ativas:<lim>:<atual>'
(P0001/raise_exception é genérico demais para distinguir por sqlstate). Aqui traduzimos isso
numa resposta 403 application/problem+json com os dados do CTA de upgrade.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

CRIA_PROBLEM_BASE = "https://cria.app/problems/"
_MARKER = "limite_obras_ativas:"


class LimiteAtivasError(Exception):
    """Limite de obras ativas atingido (soft-limit → upsell)."""

    def __init__(self, limite: int, atual: int):
        self.limite = limite
        self.atual = atual


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
