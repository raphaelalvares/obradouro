"""Portal do Cliente — pré-autorização de acesso por e-mail e reconciliação no 1º login.

O arquiteto autoriza um e-mail (no PROJETO ou direto numa OBRA); o cliente se autocadastra pelo
Supabase Auth e, no 1º login, `sincronizar` chama a RPC definer `reconciliar_acessos_cliente()` que
casa o e-mail CONFIRMADO do caller com a pré-autorização e materializa os vínculos (projeto_membros
'cliente' e, se há obra, obra_membros). Ver migration 0089. O cliente nunca lê/escreve
`acessos_cliente` direto (RLS self do arquiteto) — só o arquiteto gerencia; o vínculo é via RPC.

Revogar um acesso TAMBÉM remove o vínculo (membership) já materializado — o arquiteto, como dono,
pode deletar membros 'cliente' (RLS/guard permitem; nunca é o último arquiteto).
"""

import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit import log_event
from app.services.common import actor_name, obra_writable, projeto_writable

_SELECT_COLS = "id, email, estado, profile_id, projeto_id, obra_id, created_at"


def _acesso_out(row) -> dict:
    """Linha de acessos_cliente → shape do AcessoClienteOut (cadastrado = já entrou/vinculado)."""
    return {
        "id": row.id,
        "email": str(row.email),
        "estado": row.estado,
        "cadastrado": row.profile_id is not None,
        "projeto_id": row.projeto_id,
        "obra_id": row.obra_id,
        "created_at": row.created_at,
    }


async def _remover_vinculo_cliente(
    session: AsyncSession,
    *,
    profile_id,
    projeto_id: uuid.UUID | None = None,
    obra_id: uuid.UUID | None = None,
) -> None:
    """Ao revogar, tira o cliente do(s) vínculo(s) já materializado(s). Projeto → tira do projeto e
    da obra ligada (se houver); obra direta → tira da obra. No-op se o cliente ainda não entrou."""
    if profile_id is None:
        return
    if projeto_id is not None:
        await session.execute(
            text(
                "delete from public.projeto_membros where projeto_id = cast(:p as uuid) "
                "and profile_id = cast(:u as uuid) and papel = 'cliente'"
            ),
            {"p": str(projeto_id), "u": str(profile_id)},
        )
        await session.execute(
            text(
                "delete from public.obra_membros where profile_id = cast(:u as uuid) "
                "and papel = 'cliente' and obra_id = "
                "(select obra_id from public.projetos where id = cast(:p as uuid) "
                "and obra_id is not null)"
            ),
            {"p": str(projeto_id), "u": str(profile_id)},
        )
    if obra_id is not None:
        await session.execute(
            text(
                "delete from public.obra_membros where obra_id = cast(:o as uuid) "
                "and profile_id = cast(:u as uuid) and papel = 'cliente'"
            ),
            {"o": str(obra_id), "u": str(profile_id)},
        )


# ===================== arquiteto: acesso do cliente no PROJETO =====================
async def autorizar_acesso(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, email: str
) -> dict:
    """Pré-autoriza um e-mail como cliente do projeto (idempotente). Só o arquiteto do projeto."""
    cur = await projeto_writable(session, projeto_id)
    res = (
        await session.execute(
            text(
                f"""
                insert into public.acessos_cliente (tenant_id, projeto_id, email)
                values ((select auth.uid()), cast(:pid as uuid), :email)
                on conflict (projeto_id, email) where projeto_id is not null do nothing
                returning {_SELECT_COLS}
                """
            ),
            {"pid": str(projeto_id), "email": email},
        )
    ).first()
    if res is None:  # já autorizado: não re-audita, devolve o existente
        res = (
            await session.execute(
                text(
                    f"""select {_SELECT_COLS} from public.acessos_cliente
                       where projeto_id = cast(:pid as uuid) and email = :email"""
                ),
                {"pid": str(projeto_id), "email": email},
            )
        ).first()
        return _acesso_out(res)
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="portal.acesso_autorizado",
        entity_type="projeto",
        entity_id=projeto_id,
        changed={"email": email, "papel": "cliente"},
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return _acesso_out(res)


async def listar_acessos(session: AsyncSession, projeto_id: uuid.UUID) -> list[dict]:
    await projeto_writable(session, projeto_id)  # só arquiteto gerencia
    rows = (
        await session.execute(
            text(
                f"""select {_SELECT_COLS} from public.acessos_cliente
                   where projeto_id = cast(:pid as uuid) order by created_at"""
            ),
            {"pid": str(projeto_id)},
        )
    ).all()
    return [_acesso_out(r) for r in rows]


async def revogar_acesso(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, acesso_id: uuid.UUID
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    res = (
        await session.execute(
            text(
                """delete from public.acessos_cliente
                   where id = cast(:aid as uuid) and projeto_id = cast(:pid as uuid)
                   returning email, profile_id"""
            ),
            {"aid": str(acesso_id), "pid": str(projeto_id)},
        )
    ).first()
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "acesso não encontrado")
    await _remover_vinculo_cliente(session, profile_id=res.profile_id, projeto_id=projeto_id)
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="portal.acesso_revogado",
        entity_type="projeto",
        entity_id=projeto_id,
        changed={"email": str(res.email), "removeu_vinculo": res.profile_id is not None},
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return {"revoked": True}


# ===================== arquiteto: acesso do cliente direto na OBRA =====================
async def autorizar_acesso_obra(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, email: str
) -> dict:
    """Pré-autoriza um e-mail como cliente da obra (sem projeto). Só o arquiteto da obra."""
    cur = await obra_writable(session, obra_id)
    res = (
        await session.execute(
            text(
                f"""
                insert into public.acessos_cliente (tenant_id, obra_id, email)
                values ((select auth.uid()), cast(:oid as uuid), :email)
                on conflict (obra_id, email) where obra_id is not null do nothing
                returning {_SELECT_COLS}
                """
            ),
            {"oid": str(obra_id), "email": email},
        )
    ).first()
    if res is None:
        res = (
            await session.execute(
                text(
                    f"""select {_SELECT_COLS} from public.acessos_cliente
                       where obra_id = cast(:oid as uuid) and email = :email"""
                ),
                {"oid": str(obra_id), "email": email},
            )
        ).first()
        return _acesso_out(res)
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="portal.acesso_autorizado",
        entity_type="obra",
        entity_id=obra_id,
        changed={"email": email, "papel": "cliente"},
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return _acesso_out(res)


async def listar_acessos_obra(session: AsyncSession, obra_id: uuid.UUID) -> list[dict]:
    await obra_writable(session, obra_id)
    rows = (
        await session.execute(
            text(
                f"""select {_SELECT_COLS} from public.acessos_cliente
                   where obra_id = cast(:oid as uuid) order by created_at"""
            ),
            {"oid": str(obra_id)},
        )
    ).all()
    return [_acesso_out(r) for r in rows]


async def revogar_acesso_obra(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, acesso_id: uuid.UUID
) -> dict:
    cur = await obra_writable(session, obra_id)
    res = (
        await session.execute(
            text(
                """delete from public.acessos_cliente
                   where id = cast(:aid as uuid) and obra_id = cast(:oid as uuid)
                   returning email, profile_id"""
            ),
            {"aid": str(acesso_id), "oid": str(obra_id)},
        )
    ).first()
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "acesso não encontrado")
    await _remover_vinculo_cliente(session, profile_id=res.profile_id, obra_id=obra_id)
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="portal.acesso_revogado",
        entity_type="obra",
        entity_id=obra_id,
        changed={"email": str(res.email), "removeu_vinculo": res.profile_id is not None},
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return {"revoked": True}


# ===================== cliente: reconcilia + contexto de roteamento =====================
async def sincronizar(session: AsyncSession) -> dict:
    """Casa o e-mail confirmado do caller com as pré-autorizações e devolve o contexto de
    roteamento. Idempotente — o front chama 1× no pós-login (arquiteto só recebe eh_arquiteto)."""
    raw = (
        await session.execute(text("select public.reconciliar_acessos_cliente()"))
    ).scalar_one()
    data = json.loads(raw) if isinstance(raw, str) else raw
    return {
        "eh_arquiteto": bool(data.get("eh_arquiteto")),
        "eh_cliente": bool(data.get("eh_cliente")),
        "projetos": data.get("projetos") or [],
        "obras": data.get("obras") or [],
    }
