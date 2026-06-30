"""B6 Inc.2a: CsrfMiddleware (double-submit) e os cookies de sessão (auth_cookies)."""

from fastapi import Response
from fastapi.testclient import TestClient

from app.core import auth_cookies
from app.core.config import get_settings
from app.core.middleware import CsrfMiddleware
from app.core.security import ACCESS_COOKIE
from app.main import app
from app.services import auth as auth_svc

_client = TestClient(app)


def _cookie_header(**kv: str) -> dict:
    return {"Cookie": "; ".join(f"{k}={v}" for k, v in kv.items())}


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
def test_set_session_grava_cookies_httponly_e_devolve_csrf():
    r = Response()
    csrf = auth_cookies.set_session(r, access="atok", refresh="rtok", expires_in=3600)
    blob = " ".join(r.headers.getlist("set-cookie")).lower()
    assert csrf  # token devolvido p/ o corpo
    assert ACCESS_COOKIE in blob
    assert auth_cookies.REFRESH_COOKIE in blob
    assert auth_cookies.SEEN_COOKIE in blob
    assert auth_cookies.CSRF_COOKIE in blob
    assert "httponly" in blob


def test_refresh_seen_csrf_seguem_a_janela_e_access_fica_curto():
    """A sessão não pode durar pra sempre: refresh/seen/csrf expiram em AUTH_IDLE_TIMEOUT_SECONDS
    (6h), não nos 30 dias antigos; o access segue curto (~1h = expires_in), fora da janela."""
    s = get_settings()
    r = Response()
    auth_cookies.set_session(r, access="atok", refresh="rtok", expires_in=3600)
    cookies = [c.lower() for c in r.headers.getlist("set-cookie")]
    janela = f"max-age={s.AUTH_IDLE_TIMEOUT_SECONDS}"

    def cookie(nome: str) -> str:
        return next(c for c in cookies if c.startswith(nome.lower() + "="))

    assert janela in cookie(auth_cookies.REFRESH_COOKIE)
    assert janela in cookie(auth_cookies.SEEN_COOKIE)
    assert janela in cookie(auth_cookies.CSRF_COOKIE)
    assert "max-age=3600" in cookie(ACCESS_COOKIE)  # access NÃO herda a janela de 6h
    assert janela not in cookie(ACCESS_COOKIE)
    assert "max-age=2592000" not in " ".join(cookies)  # não regredir pros 30 dias "eternos"


def test_seen_assinado_so_valida_carimbo_intacto():
    """cria_seen é assinado (HMAC): adulterar o ts ou o mac invalida → session_inativa True."""
    bom = auth_cookies._sign_seen(1_000_000)
    assert auth_cookies._read_seen_ts(bom) == 1_000_000
    ts, _, mac = bom.partition(".")
    assert auth_cookies._read_seen_ts(f"{int(ts) + 1}.{mac}") is None  # ts mexido não casa o mac
    assert auth_cookies._read_seen_ts("1000000.deadbeef") is None
    assert auth_cookies._read_seen_ts(None) is None
    assert auth_cookies._read_seen_ts("lixo") is None


def test_session_inativa_corta_fora_da_janela_server_side():
    """Trava server-side: dentro da janela passa; ausente/adulterado/velho cai (sem o browser)."""
    s = get_settings()
    agora = 2_000_000
    fresco = auth_cookies._sign_seen(agora - 60)  # 1 min atrás
    velho = auth_cookies._sign_seen(agora - s.AUTH_IDLE_TIMEOUT_SECONDS - 1)  # logo após a janela
    assert auth_cookies.session_inativa(fresco, agora=agora) is False
    assert auth_cookies.session_inativa(velho, agora=agora) is True
    assert auth_cookies.session_inativa(None, agora=agora) is True  # sessão pré-deploy / sem cookie


# ------------------------------------------------------------------ /refresh: trava de inatividade
def test_refresh_sem_refresh_token_401():
    assert _client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_sem_seen_cai_por_inatividade_sem_chamar_gotrue():
    # refresh token presente mas SEM cria_seen (sessão pré-deploy / janela vencida): o backend corta
    # antes do GoTrue. Sem cookie de access, o CsrfMiddleware libera (não é cookie-auth).
    r = _client.post(
        "/api/v1/auth/refresh", headers=_cookie_header(**{auth_cookies.REFRESH_COOKIE: "rtok"})
    )
    assert r.status_code == 401
    assert "inatividade" in r.json()["detail"]


def test_refresh_com_seen_velho_cai_por_inatividade():
    velho = auth_cookies._sign_seen(0)  # epoch → muito além da janela
    cookies = {auth_cookies.REFRESH_COOKIE: "rtok", auth_cookies.SEEN_COOKIE: velho}
    r = _client.post("/api/v1/auth/refresh", headers=_cookie_header(**cookies))
    assert r.status_code == 401
    assert "inatividade" in r.json()["detail"]


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
