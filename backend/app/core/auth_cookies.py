"""Cookies de sessão do BFF (B6): access/refresh httpOnly + CSRF (double-submit cross-domain).

Access e refresh vão em cookies httpOnly+Secure (JS não lê → fora do alcance de XSS). O token CSRF
também vai em cookie httpOnly, MAS é devolvido no CORPO do login/refresh/session: como front e API
são cross-site, o front não lê o cookie da API — guarda o token (do corpo) em memória e reenvia no
header X-CSRF-Token. O CsrfMiddleware compara header (front) × cookie (browser). Um atacante de CSRF
não conhece o token (só veio no corpo, protegido pela SOP) → não forja o header.
"""

import hashlib
import hmac
import secrets
import time

from fastapi import Response

from app.core.config import get_settings
from app.core.security import ACCESS_COOKIE

REFRESH_COOKIE = "cria_refresh"
CSRF_COOKIE = "cria_csrf"
SEEN_COOKIE = "cria_seen"  # carimbo assinado de atividade (trava server-side de inatividade)
CSRF_HEADER = "x-csrf-token"


def _idle_max_age() -> int:
    """Validade (s) dos cookies de longa duração (refresh + csrf): a JANELA DE INATIVIDADE.

    Deslizante — re-gravada a cada login/refresh. Inativo por mais que isso → o browser descarta os
    cookies → o /refresh fica sem credencial → logout. É AQUI que mora "a sessão não dura sempre"
    (segue AUTH_IDLE_TIMEOUT_SECONDS; antes eram 30d fixos, que a mantinham viva ~indefinidamente).
    """
    return get_settings().AUTH_IDLE_TIMEOUT_SECONDS


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
        CSRF_COOKIE, token, max_age=_idle_max_age(), httponly=True, path="/", **_base_opts()
    )
    return token


def _sign_seen(ts: int) -> str:
    """Carimbo assinado `<ts>.<hmac>` (HMAC-SHA256). O cliente não consegue forjar um ts novo."""
    mac = hmac.new(get_settings().auth_session_secret, f"seen:{ts}".encode(), hashlib.sha256)
    return f"{ts}.{mac.hexdigest()}"


def _read_seen_ts(value: str | None) -> int | None:
    """Devolve o ts do cookie se a assinatura confere (constante no tempo); senão None."""
    if not value or "." not in value:
        return None
    ts_str, _, mac = value.partition(".")
    try:
        ts = int(ts_str)
    except ValueError:
        return None
    esperado = hmac.new(
        get_settings().auth_session_secret, f"seen:{ts}".encode(), hashlib.sha256
    ).hexdigest()
    return ts if hmac.compare_digest(esperado, mac) else None


def session_inativa(value: str | None, *, agora: int | None = None) -> bool:
    """Trava de inatividade do LADO SERVIDOR (não depende de o browser honrar o max-age do cookie).

    True (=cair a sessão) quando o cookie cria_seen está ausente, adulterado, ou seu último carimbo
    passou da janela AUTH_IDLE_TIMEOUT_SECONDS. O /refresh chama isto ANTES de falar com o GoTrue:
    um refresh token ainda válido no GoTrue não revive uma sessão parada há mais que a janela.
    """
    ts = _read_seen_ts(value)
    if ts is None:
        return True
    agora = int(time.time()) if agora is None else agora
    return (agora - ts) > _idle_max_age()


def set_session(response: Response, *, access: str, refresh: str, expires_in: int) -> str:
    """Grava access/refresh/seen (httpOnly) + CSRF. Devolve o token CSRF (vai também no corpo).

    Cada chamada (login/refresh/oauth) re-carimba cria_seen com agora → a janela de inatividade é
    deslizante TAMBÉM no servidor: parar de renovar por mais que a janela trava o próximo /refresh.
    """
    opts = _base_opts()
    refresh_path = get_settings().auth_refresh_cookie_path
    response.set_cookie(ACCESS_COOKIE, access, max_age=expires_in, httponly=True, path="/", **opts)
    response.set_cookie(
        REFRESH_COOKIE,
        refresh,
        max_age=_idle_max_age(),
        httponly=True,
        path=refresh_path,
        **opts,
    )
    response.set_cookie(
        SEEN_COOKIE,
        _sign_seen(int(time.time())),
        max_age=_idle_max_age(),
        httponly=True,
        path=refresh_path,
        **opts,
    )
    return issue_csrf(response)


def clear_session(response: Response) -> None:
    """Apaga os cookies de sessão (logout). Mesmo path/domain do set p/ o browser remover."""
    opts = _base_opts()
    refresh_path = get_settings().auth_refresh_cookie_path
    response.delete_cookie(ACCESS_COOKIE, path="/", **opts)
    response.delete_cookie(REFRESH_COOKIE, path=refresh_path, **opts)
    response.delete_cookie(SEEN_COOKIE, path=refresh_path, **opts)
    response.delete_cookie(CSRF_COOKIE, path="/", **opts)
