"""Operações administrativas de Auth (GoTrue Admin API via httpx, service role).

Separado do acesso a dados (RLS). Usado só pelo fluxo de convite por email, onde o arquiteto
cadastra alguém que pode ainda não ter conta. A RLS NÃO deixa o backend descobrir emails de
terceiros pela sessão do usuário — por isso a resolução do email passa pela Admin API.

Fala REST direto com o GoTrue (sem o meta-pacote `supabase`, que arrastava storage3/pyiceberg +
~30 deps inúteis aqui). A service role ignora RLS e cria contas: vive só no backend, nunca nos apps.
"""

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings

_TIMEOUT = 10.0
_PER_PAGE = 200


def _admin() -> tuple[str, dict]:
    """(base do GoTrue, headers com a service role). 503 se a auth não estiver configurada."""
    s = get_settings()
    key = s.SUPABASE_SERVICE_ROLE_KEY.get_secret_value()
    if not key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "auth não configurada")
    base = f"{s.SUPABASE_URL.rstrip('/')}/auth/v1"
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    return base, headers


async def _find_user_id_by_email(
    client: httpx.AsyncClient, base: str, headers: dict, email: str
) -> str | None:
    """Pagina /admin/users até achar o email (case-insensitive). None se não existir."""
    target = email.lower()
    page = 1
    while True:
        resp = await client.get(
            f"{base}/admin/users", params={"page": page, "per_page": _PER_PAGE}, headers=headers
        )
        resp.raise_for_status()
        data = resp.json()
        users = data.get("users", []) if isinstance(data, dict) else data
        if not users:
            return None
        for u in users:
            if (u.get("email") or "").lower() == target:
                return u["id"]
        if len(users) < _PER_PAGE:
            return None
        page += 1


async def invite_or_attach(email: str, redirect_to: str | None) -> tuple[str, bool]:
    """Convida o email. Retorna (user_id, created) — SEM link (B3: resposta uniforme, sem oráculo).

    - Novo usuário: POST /invite cria a conta E o Supabase DISPARA o email de convite (com o link
      de definir senha no template do Supabase).
    - Já existente: o GoTrue recusa (email já registrado) → resolvemos o id via /admin/users e
      seguimos; a pessoa vê o convite pendente in-app.

    Os dois caminhos NÃO devolvem link — a resposta não revela se o email já tinha conta CRIA.
    """
    base, headers = _admin()
    params = {"redirect_to": redirect_to} if redirect_to else None
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        try:
            resp = await client.post(
                f"{base}/invite", params=params, json={"email": email}, headers=headers
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            # GoTrue recusou (tipicamente: email já registrado) → tenta resolver o id existente.
            uid = await _find_user_id_by_email(client, base, headers, email)
            if uid is None:
                raise
            return uid, False
        data = resp.json()
        return (data.get("id") or (data.get("user") or {}).get("id")), True
