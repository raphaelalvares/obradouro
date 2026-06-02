"""Operações administrativas de Auth (Supabase Admin API, service role).

Separado do acesso a dados (RLS). Usado só pelo fluxo de convite por email, onde o
arquiteto cadastra alguém que pode ainda não ter conta. A RLS NÃO deixa o backend
descobrir emails de terceiros pela sessão do usuário — por isso a resolução do email
passa obrigatoriamente pela Admin API.
"""

from app.core.supabase import create_supabase_admin

_admin = None


async def _get_admin():
    # Cache simples no nível do módulo (evita recriar o client httpx a cada chamada).
    global _admin
    if _admin is None:
        _admin = await create_supabase_admin()
    return _admin


async def _find_user_id_by_email(admin, email: str) -> str | None:
    page = 1
    target = email.lower()
    while True:
        users = await admin.auth.admin.list_users(page=page, per_page=200)
        if not users:
            return None
        for u in users:
            if (getattr(u, "email", None) or "").lower() == target:
                return u.id
        if len(users) < 200:
            return None
        page += 1


async def invite_or_attach(email: str, redirect_to: str | None) -> tuple[str, str | None, bool]:
    """Resolve o usuário do email. Retorna (user_id, action_link, created).

    - Novo usuário: generate_link type=invite cria a conta E devolve o link de definir senha.
    - Já existente: acha o id (sem link de convite — a pessoa vê o convite pendente in-app).
    """
    admin = await _get_admin()
    params: dict = {"type": "invite", "email": email}
    if redirect_to:
        params["options"] = {"redirect_to": redirect_to}
    try:
        resp = await admin.auth.admin.generate_link(params)
        return resp.user.id, resp.properties.action_link, True
    except Exception:
        uid = await _find_user_id_by_email(admin, email)
        if uid is None:
            raise
        return uid, None, False
