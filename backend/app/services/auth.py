"""Auth BFF (B6): chamadas REST diretas ao GoTrue do Supabase (login/refresh/logout).

Stateless — o backend NÃO guarda sessão; só troca credenciais por tokens e os repassa em cookies
httpOnly (app.core.auth_cookies). Erros viram 401 com mensagem GENÉRICA (não vaza se o email existe
nem o motivo interno). Signup e OAuth entram nos próximos incrementos (2b/2c).
"""

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings

_TIMEOUT = 10.0


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
