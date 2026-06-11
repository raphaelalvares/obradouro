"""Auth BFF (B6): chamadas REST diretas ao GoTrue do Supabase (login/refresh/logout).

Stateless — o backend NÃO guarda sessão; só troca credenciais por tokens e os repassa em cookies
httpOnly (app.core.auth_cookies). Erros viram 401 com mensagem GENÉRICA (não vaza se o email existe
nem o motivo interno). Signup e OAuth entram nos próximos incrementos (2b/2c).
"""

import base64
import hashlib
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings

_TIMEOUT = 10.0
OAUTH_PROVIDERS = {"google", "apple"}


def _gotrue() -> tuple[str, str]:
    s = get_settings()
    if not s.SUPABASE_ANON_KEY:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "auth não configurada")
    return f"{s.SUPABASE_URL.rstrip('/')}/auth/v1", s.SUPABASE_ANON_KEY.get_secret_value()


async def _token(grant: str, body: dict) -> dict:
    base, key = _gotrue()
    headers = {"apikey": key, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{base}/token", params={"grant_type": grant}, json=body, headers=headers
        )
    if resp.status_code >= 400:
        # genérico: não distingue email-inexistente de senha-errada de refresh-expirado.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "credenciais inválidas")
    return resp.json()


async def login(email: str, password: str) -> dict:
    """Troca email+senha por uma sessão (access_token, refresh_token, expires_in, user)."""
    return await _token("password", {"email": email, "password": password})


async def signup(email: str, password: str, *, nome: str, telefone: str | None) -> dict:
    """Cria a conta no GoTrue com o metadata (nome/telefone/aceite). Devolve sessão (autoconfirm)
    OU só o user (se o projeto exige confirmação de email — aí não vem token)."""
    base, key = _gotrue()
    headers = {"apikey": key, "Content-Type": "application/json"}
    body = {
        "email": email,
        "password": password,
        "data": {"nome": nome, "telefone": telefone, "aceite": True},
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(f"{base}/signup", json=body, headers=headers)
    if resp.status_code >= 400:
        # email já cadastrado / senha fraca / etc. GoTrue detalha; respondemos genérico.
        code = status.HTTP_422_UNPROCESSABLE_ENTITY if resp.status_code < 500 else 400
        raise HTTPException(code, "não foi possível cadastrar")
    return resp.json()


def session_or_pending(data: dict) -> tuple[str | None, bool]:
    """(user_id, tem_sessao). GoTrue /signup devolve sessão (autoconfirm: tem access_token) OU só o
    user (confirmação de email ligada: os campos do user vêm no topo ou sob 'user')."""
    if data.get("access_token"):
        return data["user"]["id"], True
    return data.get("id") or (data.get("user") or {}).get("id"), False


async def refresh(refresh_token: str) -> dict:
    """Troca o refresh_token por uma sessão nova (rotação de tokens)."""
    return await _token("refresh_token", {"refresh_token": refresh_token})


async def logout(access_token: str) -> None:
    """Revoga a sessão no Supabase (best-effort — os cookies são limpos de qualquer forma)."""
    base, key = _gotrue()
    headers = {"apikey": key, "Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            await client.post(f"{base}/logout", headers=headers)
    except httpx.HTTPError:
        pass


# ---------------------------------------------------------------- OAuth (2c, PKCE server-side)
def gen_pkce() -> tuple[str, str]:
    """(code_verifier, code_challenge S256). O verifier fica num cookie curto até o callback."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def oauth_authorize_url(provider: str, code_challenge: str) -> str:
    """URL do GoTrue /authorize que leva o browser ao provedor; volta no nosso /auth/callback."""
    s = get_settings()
    if not s.api_base_url:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "OAuth não configurado")
    query = urlencode(
        {
            "provider": provider,
            "redirect_to": s.oauth_callback_url,
            "code_challenge": code_challenge,
            "code_challenge_method": "s256",
        }
    )
    return f"{s.SUPABASE_URL.rstrip('/')}/auth/v1/authorize?{query}"


async def exchange_pkce(code: str, verifier: str) -> dict:
    """Troca o code (do callback) + verifier por uma sessão (grant_type=pkce)."""
    return await _token("pkce", {"auth_code": code, "code_verifier": verifier})
