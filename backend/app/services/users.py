"""Operações administrativas de Auth (GoTrue Admin API via httpx, service role).

Separado do acesso a dados (RLS). Usado pelo painel de suporte da plataforma (status da conta,
reenviar confirmação, link de reset, ban/reativar) — operações que a RLS não permite a partir da
sessão do usuário.

Fala REST direto com o GoTrue (sem o meta-pacote `supabase`, que arrastava storage3/pyiceberg +
~30 deps inúteis aqui). A service role ignora RLS: vive só no backend, nunca nos apps.
"""

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings

_TIMEOUT = 10.0


def _admin() -> tuple[str, dict]:
    """(base do GoTrue, headers com a service role). 503 se a auth não estiver configurada."""
    s = get_settings()
    key = s.SUPABASE_SERVICE_ROLE_KEY.get_secret_value()
    if not key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "auth não configurada")
    base = f"{s.SUPABASE_URL.rstrip('/')}/auth/v1"
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    return base, headers


# ===================== suporte ao usuário (painel admin) =====================
# profiles.id == auth.users.id == tenant_id → operamos no GoTrue direto pelo tenant_id.
async def _get_user(client: httpx.AsyncClient, base: str, headers: dict, user_id: str) -> dict:
    resp = await client.get(f"{base}/admin/users/{user_id}", headers=headers)
    resp.raise_for_status()
    return resp.json()


def _falha_auth(e: httpx.HTTPStatusError) -> HTTPException:
    return HTTPException(status.HTTP_502_BAD_GATEWAY, "falha na operação de auth")


async def status_usuario(user_id: str) -> dict:
    """Status do e-mail/conta p/ diagnosticar 'não consigo entrar': confirmado? suspenso?"""
    base, headers = _admin()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            u = await _get_user(client, base, headers, user_id)
        except httpx.HTTPStatusError as e:
            raise _falha_auth(e) from e
    banido_ate = u.get("banned_until")
    return {
        "email": u.get("email"),
        "email_confirmado": bool(u.get("email_confirmed_at")),
        "banido": bool(banido_ate) and banido_ate != "none",
    }


async def reenviar_confirmacao(user_id: str) -> None:
    """Reenvia o e-mail de confirmação (Supabase dispara o template). 409 se já confirmado."""
    base, headers = _admin()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            u = await _get_user(client, base, headers, user_id)
            email = u.get("email")
            if not email:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "usuário sem e-mail")
            if u.get("email_confirmed_at"):
                raise HTTPException(status.HTTP_409_CONFLICT, "e-mail já confirmado")
            resp = await client.post(
                f"{base}/resend", json={"type": "signup", "email": email}, headers=headers
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise _falha_auth(e) from e


async def link_reset_senha(user_id: str) -> str:
    """Gera um link de redefinição de senha (recovery) p/ o admin repassar ao usuário travado."""
    base, headers = _admin()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            u = await _get_user(client, base, headers, user_id)
            email = u.get("email")
            if not email:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "usuário sem e-mail")
            resp = await client.post(
                f"{base}/admin/generate_link",
                json={"type": "recovery", "email": email},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            raise _falha_auth(e) from e
    return data.get("action_link") or (data.get("properties") or {}).get("action_link") or ""


async def definir_ban(user_id: str, banir: bool) -> None:
    """Suspende (ban longo) ou reativa (ban 'none') o acesso de um usuário."""
    base, headers = _admin()
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.put(
                f"{base}/admin/users/{user_id}",
                json={"ban_duration": "876000h" if banir else "none"},
                headers=headers,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise _falha_auth(e) from e
