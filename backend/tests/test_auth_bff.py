"""B6 Inc.2a: CsrfMiddleware (double-submit) e os cookies de sessão (auth_cookies)."""

from fastapi import Response

from app.core import auth_cookies
from app.core.middleware import CsrfMiddleware
from app.core.security import ACCESS_COOKIE
from app.services import auth as auth_svc


# ------------------------------------------------------------------ CsrfMiddleware
async def _inner(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def _run(
    method: str, headers: list[tuple[bytes, bytes]], path: str = "/api/v1/recurso"
) -> int:
    mw = CsrfMiddleware(_inner)
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    scope = {"type": "http", "method": method, "headers": headers, "path": path}
    await mw(scope, receive, send)
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


async def test_csrf_post_login_isento_mesmo_com_cookie_velho():
    # /auth/login bootstrapa credencial → isento; destrava o re-login com cria_access preso (sem
    # header CSRF, que num recurso normal daria 403 — ver teste acima).
    headers = [(b"cookie", b"cria_access=tok; cria_csrf=abc")]
    assert await _run("POST", headers, path="/api/v1/auth/login") == 200


async def test_csrf_post_signup_isento_mesmo_com_cookie_velho():
    headers = [(b"cookie", b"cria_access=tok; cria_csrf=abc")]
    assert await _run("POST", headers, path="/api/v1/auth/signup") == 200


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


# ------------------------------------------------------------------ signup (2b): parsing GoTrue
def test_signup_com_sessao_autoconfirm():
    data = {"access_token": "a", "refresh_token": "r", "user": {"id": "u1"}}
    assert auth_svc.session_or_pending(data) == ("u1", True)


def test_signup_pendente_user_no_topo():  # confirmação de email ligada
    assert auth_svc.session_or_pending({"id": "u2", "email": "x@y.z"}) == ("u2", False)


def test_signup_pendente_user_aninhado():
    assert auth_svc.session_or_pending({"user": {"id": "u3"}}) == ("u3", False)


# ------------------------------------------------------------------ OAuth PKCE (2c)
def test_gen_pkce_challenge_e_s256_do_verifier():
    import base64
    import hashlib

    verifier, challenge = auth_svc.gen_pkce()
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    assert challenge == expected
    assert "=" not in challenge  # base64url sem padding
    assert verifier != challenge
