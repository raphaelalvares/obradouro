"""B6 Inc.2a: CsrfMiddleware (double-submit) e os cookies de sessão (auth_cookies)."""

from fastapi import Response

from app.core import auth_cookies
from app.core.middleware import CsrfMiddleware
from app.core.security import ACCESS_COOKIE


# ------------------------------------------------------------------ CsrfMiddleware
async def _inner(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def _run(method: str, headers: list[tuple[bytes, bytes]]) -> int:
    mw = CsrfMiddleware(_inner)
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    await mw({"type": "http", "method": method, "headers": headers}, receive, send)
    return next(m for m in sent if m["type"] == "http.response.start")["status"]


async def test_csrf_get_com_cookie_passa():  # método seguro nunca exige CSRF
    assert await _run("GET", [(b"cookie", b"cria_access=tok")]) == 200


async def test_csrf_post_sem_cookie_passa():  # Bearer/legado (sem cookie de sessão)
    assert await _run("POST", [(b"authorization", b"Bearer x")]) == 200


async def test_csrf_post_cookie_sem_header_bloqueia():
    assert await _run("POST", [(b"cookie", b"cria_access=tok; cria_csrf=abc")]) == 403


async def test_csrf_post_cookie_header_casado_passa():
    headers = [(b"cookie", b"cria_access=tok; cria_csrf=abc"), (b"x-csrf-token", b"abc")]
    assert await _run("POST", headers) == 200


async def test_csrf_post_cookie_header_divergente_bloqueia():
    headers = [(b"cookie", b"cria_access=tok; cria_csrf=abc"), (b"x-csrf-token", b"zzz")]
    assert await _run("POST", headers) == 403


# ------------------------------------------------------------------ auth_cookies
def test_set_session_grava_3_cookies_httponly_e_devolve_csrf():
    r = Response()
    csrf = auth_cookies.set_session(r, access="atok", refresh="rtok", expires_in=3600)
    blob = " ".join(r.headers.getlist("set-cookie")).lower()
    assert csrf  # token devolvido p/ o corpo
    assert ACCESS_COOKIE in blob
    assert auth_cookies.REFRESH_COOKIE in blob
    assert auth_cookies.CSRF_COOKIE in blob
    assert "httponly" in blob


def test_clear_session_expira_os_cookies():
    r = Response()
    auth_cookies.clear_session(r)
    blob = " ".join(r.headers.getlist("set-cookie")).lower()
    assert ACCESS_COOKIE in blob and "max-age=0" in blob
