"""Cookies de sessão do BFF (B6): access/refresh httpOnly + CSRF (double-submit cross-domain).

Access e refresh vão em cookies httpOnly+Secure (JS não lê → fora do alcance de XSS). O token CSRF
também vai em cookie httpOnly, MAS é devolvido no CORPO do login/refresh/session: como front e API
são cross-site, o front não lê o cookie da API — guarda o token (do corpo) em memória e reenvia no
header X-CSRF-Token. O CsrfMiddleware compara header (front) × cookie (browser). Um atacante de CSRF
não conhece o token (só veio no corpo, protegido pela SOP) → não forja o header.
"""

import secrets

from fastapi import Response

from app.core.config import get_settings
from app.core.security import ACCESS_COOKIE

REFRESH_COOKIE = "cria_refresh"
CSRF_COOKIE = "cria_csrf"
CSRF_HEADER = "x-csrf-token"

_REFRESH_MAX_AGE = 60 * 60 * 24 * 30  # 30 dias


def _base_opts() -> dict:
    s = get_settings()
    return {
        "secure": s.AUTH_COOKIE_SECURE,
        "samesite": s.AUTH_COOKIE_SAMESITE,
        "domain": s.AUTH_COOKIE_DOMAIN,
    }


def issue_csrf(response: Response) -> str:
    """Gera e grava o cookie CSRF (httpOnly). Devolve o token p/ o front guardar em memória."""
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE, token, max_age=_REFRESH_MAX_AGE, httponly=True, path="/", **_base_opts()
    )
    return token


def set_session(response: Response, *, access: str, refresh: str, expires_in: int) -> str:
    """Grava access/refresh (httpOnly) + CSRF. Devolve o token CSRF (vai também no corpo)."""
    opts = _base_opts()
    response.set_cookie(ACCESS_COOKIE, access, max_age=expires_in, httponly=True, path="/", **opts)
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=_REFRESH_MAX_AGE,
        httponly=True,
        path=get_settings().auth_refresh_cookie_path,
        **opts,
    )
    return issue_csrf(response)


def clear_session(response: Response) -> None:
    """Apaga os 3 cookies (logout). Mesmo path/domain do set p/ o browser de fato remover."""
    opts = _base_opts()
    response.delete_cookie(ACCESS_COOKIE, path="/", **opts)
    response.delete_cookie(
        REFRESH_COOKIE, path=get_settings().auth_refresh_cookie_path, **opts
    )
    response.delete_cookie(CSRF_COOKIE, path="/", **opts)
