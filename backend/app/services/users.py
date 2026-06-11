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


async def invite_or_attach(email: str, redirect_to: str | None) -> tuple[str, bool]:
    """Convida o email. Retorna (user_id, created) — SEM link (B3: resposta uniforme, sem oráculo).

    - Novo usuário: invite_user_by_email cria a conta E o Supabase DISPARA o email de convite
      (com o link de definir senha no template do Supabase).
    - Já existente: a Admin API recusa (email já registrado) → resolvemos o id e seguimos; a pessoa
      vê o convite pendente in-app.

    Os dois caminhos NÃO devolvem link — a resposta não revela se o email já tinha conta CRIA.
    """
    admin = await _get_admin()
    options = {"redirect_to": redirect_to} if redirect_to else None
    try:
        resp = await admin.auth.admin.invite_user_by_email(email, options)
        return resp.user.id, True
    except Exception:
        uid = await _find_user_id_by_email(admin, email)
        if uid is None:
            raise
        return uid, False
