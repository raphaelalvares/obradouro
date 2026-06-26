"""Blindagem do painel admin (red-report 2026-06).

Garante, de forma ESTÁTICA (sem DB), os invariantes que impedem um usuário de aplicação se
autoconceder admin da plataforma. Pega regressão se alguém remover o REVOKE/trigger da 0095,
reconceder a tabela platform_admins a uma role de aplicação, ou criar uma policy permissiva nela.
"""

import pathlib
import re

MIGR = pathlib.Path(__file__).resolve().parents[2] / "supabase" / "migrations"
BLINDAGEM = MIGR / "0095_blindar_platform_admins.sql"


def test_0095_revoga_tabela_das_roles_de_app():
    sql = BLINDAGEM.read_text(encoding="utf-8").lower()
    assert "revoke all on table public.platform_admins from anon, authenticated, public" in sql


def test_0095_instala_trigger_de_lockdown():
    sql = BLINDAGEM.read_text(encoding="utf-8").lower()
    assert "create trigger trg_platform_admins_lockdown" in sql
    assert "before insert or update or delete on public.platform_admins" in sql


def test_0095_lockdown_e_security_invoker_e_barra_roles_de_app():
    """A função de lockdown NÃO pode ser SECURITY DEFINER — senão current_user seria sempre o owner
    (postgres) e a trava nunca pegaria a escrita direta de 'authenticated'."""
    sql = BLINDAGEM.read_text(encoding="utf-8")
    func = re.search(
        r"create or replace function public\.platform_admins_lockdown\(\).*?\$\$;", sql, re.S
    )
    assert func, "função de lockdown não encontrada"
    corpo = func.group(0).lower()
    assert "security definer" not in corpo
    for role in ("authenticated", "anon", "cria_app"):
        assert role in corpo, role


def test_nenhuma_migration_concede_tabela_platform_admins_a_role_de_app():
    """Nenhuma migration pode dar GRANT de TABELA em platform_admins p/ role de app.

    (grants em FUNÇÃO is_platform_admin/admin_* são OK e não casam — a tabela tem 's' final.)
    """
    grant_stmt = re.compile(r"grant[^;]*\bplatform_admins\b[^;]*;", re.I)
    role_alvo = re.compile(r"\bto\b[^;]*\b(anon|authenticated|cria_app)\b", re.I)
    for f in MIGR.glob("*.sql"):
        for m in grant_stmt.finditer(f.read_text(encoding="utf-8")):
            stmt = m.group(0)
            if "on function" in stmt.lower():
                continue  # grant em função, não na tabela
            assert not role_alvo.search(stmt), (f.name, stmt)


def test_platform_admins_sem_policy_permissiva():
    """platform_admins fica default-deny (sem policy) — 2a trava além do revoke/trigger."""
    pat = re.compile(r"create policy[^;]*on\s+public\.platform_admins", re.I | re.S)
    for f in MIGR.glob("*.sql"):
        assert not pat.search(f.read_text(encoding="utf-8")), f.name
