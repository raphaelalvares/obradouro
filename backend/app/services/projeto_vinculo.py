"""Vínculo do PROJETO (espelha o da obra, Fase 1): membros, convite por email, aceite, código.
Projeto é arquiteto↔cliente — papel concedido é sempre 'cliente' (prestador barrado no guard 0040).
"""

import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.audit import log_event
from app.services.common import actor_name, projeto_writable
from app.services.users import invite_or_attach

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sem ambíguos


def _gen_code(n: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(n))


# ============================ membros ============================
async def list_membros(session: AsyncSession, projeto_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                select m.id, m.profile_id, p.nome, p.email, m.papel, m.estado, m.created_at
                from public.projeto_membros m
                join public.profiles p on p.id = m.profile_id
                where m.projeto_id = cast(:id as uuid)
                order by m.created_at
                """
            ),
            {"id": str(projeto_id)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def remove_membro(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, membro_id: uuid.UUID
) -> dict:
    cur = await projeto_writable(session, projeto_id)  # só arquiteto
    target = (
        await session.execute(
            text(
                """
                select m.papel, m.estado, p.nome as membro_nome
                from public.projeto_membros m
                join public.profiles p on p.id = m.profile_id
                where m.id = cast(:mid as uuid) and m.projeto_id = cast(:pid as uuid)
                """
            ),
            {"mid": str(membro_id), "pid": str(projeto_id)},
        )
    ).first()
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "membro não encontrado")
    if target.papel == "arquiteto" and target.estado == "ativo":
        n_arq = (
            await session.execute(
                text(
                    """select count(*) from public.projeto_membros
                       where projeto_id = cast(:pid as uuid) and papel = 'arquiteto'
                         and estado = 'ativo'"""
                ),
                {"pid": str(projeto_id)},
            )
        ).scalar_one()
        if n_arq <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "não é possível remover o último arquiteto do projeto"
            )
    await session.execute(
        text("delete from public.projeto_membros where id = cast(:mid as uuid)"),
        {"mid": str(membro_id)},
    )
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="membro.removido",
        entity_type="projeto_membro",
        entity_id=membro_id,
        changed={"papel": target.papel},
        entity_label=target.membro_nome or "membro",
        actor_label=await actor_name(session),
    )
    return {"removed": True}


# ============================ convite por email ============================
async def convidar_por_email(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, email: str
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    settings = get_settings()
    invitee_id, action_link, _created = await invite_or_attach(email, settings.INVITE_REDIRECT_URL)
    res = (
        await session.execute(
            text(
                """
                insert into public.projeto_membros
                    (projeto_id, profile_id, papel, estado, invited_by)
                values (cast(:pid as uuid), cast(:uid as uuid), 'cliente', 'pendente',
                        (select auth.uid()))
                on conflict (projeto_id, profile_id) do nothing
                returning estado
                """
            ),
            {"pid": str(projeto_id), "uid": str(invitee_id)},
        )
    ).first()
    if res is None:  # já era membro/convidado: não reenvia nem re-audita
        atual = (
            await session.execute(
                text(
                    """select estado from public.projeto_membros
                       where projeto_id = cast(:pid as uuid) and profile_id = cast(:uid as uuid)"""
                ),
                {"pid": str(projeto_id), "uid": str(invitee_id)},
            )
        ).first()
        return {
            "profile_id": invitee_id,
            "estado": atual.estado if atual else "pendente",
            "action_link": None,
        }
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="convite.enviado",
        entity_type="projeto",
        entity_id=projeto_id,
        changed={"email": email, "papel": "cliente"},
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return {"profile_id": invitee_id, "estado": "pendente", "action_link": action_link}


async def aceitar_convite(session: AsyncSession, user_id: str, membro_id: uuid.UUID) -> dict:
    res = (
        await session.execute(
            text(
                """update public.projeto_membros set estado = 'ativo'
                   where id = cast(:mid as uuid)
                     and profile_id = (select auth.uid())
                     and estado = 'pendente'
                   returning projeto_id"""
            ),
            {"mid": str(membro_id)},
        )
    ).first()
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "convite pendente não encontrado")
    projeto_id = res.projeto_id
    proj = (
        await session.execute(
            text("select nome, seq_humano from public.projetos where id = cast(:id as uuid)"),
            {"id": str(projeto_id)},
        )
    ).first()
    await log_event(
        session,
        tenant=user_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="convite.aceito",
        entity_type="projeto",
        entity_id=projeto_id,
        entity_label=proj.nome if proj else "projeto",
        entity_seq=proj.seq_humano if proj else None,
        actor_label=await actor_name(session),
    )
    return {"projeto_id": projeto_id, "estado": "ativo"}


async def listar_pendentes(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """select projeto_id, projeto_nome, seq_humano, invited_by_nome
                   from public.minhas_inscricoes_projeto_pendentes()"""
            )
        )
    ).all()
    return [dict(r._mapping) for r in rows]


# ============================ código de projeto ============================
async def gerar_codigo(session: AsyncSession, user_id: str, projeto_id: uuid.UUID) -> dict:
    cur = await projeto_writable(session, projeto_id)
    await session.execute(
        text("select pg_advisory_xact_lock(hashtextextended(:pid, 0))"),
        {"pid": str(projeto_id)},
    )
    await session.execute(
        text(
            """update public.projeto_codigos set revoked_at = now()
               where projeto_id = cast(:pid as uuid) and revoked_at is null"""
        ),
        {"pid": str(projeto_id)},
    )
    row = None
    for _ in range(5):
        code = _gen_code()
        try:
            async with session.begin_nested():
                row = (
                    await session.execute(
                        text(
                            """
                            insert into public.projeto_codigos
                                (projeto_id, codigo, papel, expires_at, created_by)
                            values (cast(:pid as uuid), :code, 'cliente',
                                    now() + interval '24 hours', (select auth.uid()))
                            returning codigo, papel, expires_at
                            """
                        ),
                        {"pid": str(projeto_id), "code": code},
                    )
                ).first()
            break
        except IntegrityError:
            row = None
            continue
    if row is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "não foi possível gerar código")
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="codigo.gerado",
        entity_type="projeto",
        entity_id=projeto_id,
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return dict(row._mapping)


async def get_codigo_ativo(session: AsyncSession, projeto_id: uuid.UUID) -> dict:
    await projeto_writable(session, projeto_id)
    row = (
        await session.execute(
            text(
                """select codigo, papel, expires_at from public.projeto_codigos
                   where projeto_id = cast(:pid as uuid)
                     and revoked_at is null and expires_at > now()"""
            ),
            {"pid": str(projeto_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "nenhum código ativo")
    return dict(row._mapping)


async def revogar_codigo(session: AsyncSession, user_id: str, projeto_id: uuid.UUID) -> dict:
    cur = await projeto_writable(session, projeto_id)
    res = (
        await session.execute(
            text(
                """update public.projeto_codigos set revoked_at = now()
                   where projeto_id = cast(:pid as uuid) and revoked_at is null returning id"""
            ),
            {"pid": str(projeto_id)},
        )
    ).first()
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "nenhum código ativo")
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="codigo.revogado",
        entity_type="projeto",
        entity_id=projeto_id,
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return {"revoked": True}


async def resgatar(session: AsyncSession, codigo: str) -> dict:
    """Entra no projeto como PENDENTE (RPC definer). Devolve o estado p/ o backend dar feedback."""
    try:
        row = (
            await session.execute(
                text(
                    "select projeto_id, estado from public.resgatar_codigo_projeto(:c)"
                ),
                {"c": codigo},
            )
        ).first()
    except DBAPIError as e:
        sqlstate = getattr(getattr(e, "orig", None), "sqlstate", None)
        if sqlstate == "22023":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "código inválido ou expirado") from e
        raise
    return {"projeto_id": row.projeto_id, "estado": row.estado}
