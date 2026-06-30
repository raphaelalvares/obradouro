"""Portal do Cliente — pré-autorização de acesso por e-mail e reconciliação no 1º login.

O arquiteto autoriza um e-mail (no PROJETO ou direto numa OBRA) com um PRAZO de validade; o cliente
se autocadastra pelo Supabase Auth e, no 1º login, `sincronizar` chama a RPC definer
`reconciliar_acessos_cliente()` que casa o e-mail CONFIRMADO do caller com a pré-autorização e
materializa os vínculos (projeto_membros 'cliente' e, se há obra, obra_membros) já carimbando o
`expira_em`. No vencimento o acesso é BLOQUEADO no RLS (migration 0096). O cliente nunca lê/escreve
`acessos_cliente` direto (RLS self do arquiteto) — só o arquiteto gerencia; o vínculo é via RPC.

Revogar um acesso TAMBÉM remove o vínculo (membership) já materializado.
"""

import datetime as dt
import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit import log_event
from app.services.common import actor_name, obra_writable, projeto_writable

_COLS = (
    "id, email, estado, profile_id, projeto_id, obra_id, "
    "validade_tipo, validade_ate, created_at"
)
# expira_em DERIVADO (não é coluna): 'data' → o dia inteiro; 'entrega' → a entrega da obra alvo
# (direta ou via projeto); 'sem_prazo' → null. Espelha a regra de aplicar_validade_acesso (0096).
_EXPIRA = """
    case
      when ac.validade_tipo = 'data'
        then (ac.validade_ate + 1)::timestamp at time zone 'America/Sao_Paulo'
      when ac.validade_tipo = 'entrega' then (
        select o.entregue_em from public.obras o
        where o.id = coalesce(ac.obra_id,
              (select pj.obra_id from public.projetos pj where pj.id = ac.projeto_id))
      )
      else null
    end as expira_em
"""


def _acesso_out(row) -> dict:
    """Linha de acessos_cliente → AcessoClienteOut (cadastrado = já entrou; expirado derivado)."""
    expira = getattr(row, "expira_em", None)
    now = dt.datetime.now(dt.UTC)
    return {
        "id": row.id,
        "email": str(row.email),
        "estado": row.estado,
        "cadastrado": row.profile_id is not None,
        "validade_tipo": row.validade_tipo,
        "validade_ate": row.validade_ate,
        "expira_em": expira,
        "expirado": bool(expira is not None and expira <= now),
        "projeto_id": row.projeto_id,
        "obra_id": row.obra_id,
        "created_at": row.created_at,
    }


async def _sel_by_id(session: AsyncSession, acesso_id: uuid.UUID):
    return (
        await session.execute(
            text(f"select {_COLS}, {_EXPIRA} from public.acessos_cliente ac where ac.id = :aid"),
            {"aid": str(acesso_id)},
        )
    ).first()


async def _remover_vinculo_cliente(
    session: AsyncSession,
    *,
    profile_id,
    projeto_id: uuid.UUID | None = None,
    obra_id: uuid.UUID | None = None,
) -> None:
    """Ao revogar, tira o cliente do(s) vínculo(s) materializado(s). No-op se ainda não entrou."""
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
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    email: str,
    validade_tipo: str = "sem_prazo",
    validade_ate: dt.date | None = None,
) -> dict:
    """Pré-autoriza um e-mail como cliente do projeto (idempotente). Só o arquiteto do projeto."""
    cur = await projeto_writable(session, projeto_id)
    novo = (
        await session.execute(
            text(
                """
                insert into public.acessos_cliente
                  (tenant_id, projeto_id, email, validade_tipo, validade_ate)
                values ((select auth.uid()), cast(:pid as uuid), :email, :t, :d)
                on conflict (projeto_id, email) where projeto_id is not null do nothing
                returning id
                """
            ),
            {"pid": str(projeto_id), "email": email, "t": validade_tipo, "d": validade_ate},
        )
    ).first()
    row = (
        await session.execute(
            text(
                f"select {_COLS}, {_EXPIRA} from public.acessos_cliente ac "
                "where ac.projeto_id = cast(:pid as uuid) and ac.email = :email"
            ),
            {"pid": str(projeto_id), "email": email},
        )
    ).first()
    if novo is None:  # já autorizado: não re-audita (prazo se muda pelo PATCH)
        return _acesso_out(row)
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="portal.acesso_autorizado",
        entity_type="projeto",
        entity_id=projeto_id,
        changed={"email": email, "papel": "cliente", "validade_tipo": validade_tipo},
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return _acesso_out(row)


async def listar_acessos(session: AsyncSession, projeto_id: uuid.UUID) -> list[dict]:
    await projeto_writable(session, projeto_id)  # só arquiteto gerencia
    rows = (
        await session.execute(
            text(
                f"select {_COLS}, {_EXPIRA} from public.acessos_cliente ac "
                "where ac.projeto_id = cast(:pid as uuid) order by ac.created_at"
            ),
            {"pid": str(projeto_id)},
        )
    ).all()
    return [_acesso_out(r) for r in rows]


async def definir_prazo_acesso(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    acesso_id: uuid.UUID,
    validade_tipo: str,
    validade_ate: dt.date | None,
) -> dict:
    """Define/renova o prazo de um acesso do projeto e reaplica o expira_em na membership."""
    cur = await projeto_writable(session, projeto_id)
    upd = (
        await session.execute(
            text(
                """update public.acessos_cliente set validade_tipo = :t, validade_ate = :d
                   where id = cast(:aid as uuid) and projeto_id = cast(:pid as uuid)
                   returning email"""
            ),
            {"t": validade_tipo, "d": validade_ate, "aid": str(acesso_id), "pid": str(projeto_id)},
        )
    ).first()
    if upd is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "acesso não encontrado")
    await session.execute(
        text("select public.aplicar_validade_acesso(cast(:aid as uuid))"),
        {"aid": str(acesso_id)},
    )
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="portal.acesso_prazo",
        entity_type="projeto",
        entity_id=projeto_id,
        changed={"email": str(upd.email), "validade_tipo": validade_tipo,
                 "validade_ate": str(validade_ate) if validade_ate else None},
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return _acesso_out(await _sel_by_id(session, acesso_id))


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
    session: AsyncSession,
    user_id: str,
    obra_id: uuid.UUID,
    email: str,
    validade_tipo: str = "sem_prazo",
    validade_ate: dt.date | None = None,
) -> dict:
    """Pré-autoriza um e-mail como cliente da obra (sem projeto). Só o arquiteto da obra."""
    cur = await obra_writable(session, obra_id)
    novo = (
        await session.execute(
            text(
                """
                insert into public.acessos_cliente
                  (tenant_id, obra_id, email, validade_tipo, validade_ate)
                values ((select auth.uid()), cast(:oid as uuid), :email, :t, :d)
                on conflict (obra_id, email) where obra_id is not null do nothing
                returning id
                """
            ),
            {"oid": str(obra_id), "email": email, "t": validade_tipo, "d": validade_ate},
        )
    ).first()
    row = (
        await session.execute(
            text(
                f"select {_COLS}, {_EXPIRA} from public.acessos_cliente ac "
                "where ac.obra_id = cast(:oid as uuid) and ac.email = :email"
            ),
            {"oid": str(obra_id), "email": email},
        )
    ).first()
    if novo is None:
        return _acesso_out(row)
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="portal.acesso_autorizado",
        entity_type="obra",
        entity_id=obra_id,
        changed={"email": email, "papel": "cliente", "validade_tipo": validade_tipo},
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return _acesso_out(row)


async def listar_acessos_obra(session: AsyncSession, obra_id: uuid.UUID) -> list[dict]:
    await obra_writable(session, obra_id)
    rows = (
        await session.execute(
            text(
                f"select {_COLS}, {_EXPIRA} from public.acessos_cliente ac "
                "where ac.obra_id = cast(:oid as uuid) order by ac.created_at"
            ),
            {"oid": str(obra_id)},
        )
    ).all()
    return [_acesso_out(r) for r in rows]


async def definir_prazo_acesso_obra(
    session: AsyncSession,
    user_id: str,
    obra_id: uuid.UUID,
    acesso_id: uuid.UUID,
    validade_tipo: str,
    validade_ate: dt.date | None,
) -> dict:
    """Define/renova o prazo de um acesso da obra e reaplica o expira_em na membership."""
    cur = await obra_writable(session, obra_id)
    upd = (
        await session.execute(
            text(
                """update public.acessos_cliente set validade_tipo = :t, validade_ate = :d
                   where id = cast(:aid as uuid) and obra_id = cast(:oid as uuid)
                   returning email"""
            ),
            {"t": validade_tipo, "d": validade_ate, "aid": str(acesso_id), "oid": str(obra_id)},
        )
    ).first()
    if upd is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "acesso não encontrado")
    await session.execute(
        text("select public.aplicar_validade_acesso(cast(:aid as uuid))"),
        {"aid": str(acesso_id)},
    )
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="portal.acesso_prazo",
        entity_type="obra",
        entity_id=obra_id,
        changed={"email": str(upd.email), "validade_tipo": validade_tipo,
                 "validade_ate": str(validade_ate) if validade_ate else None},
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return _acesso_out(await _sel_by_id(session, acesso_id))


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
    roteamento. Idempotente — o front chama 1× no pós-login. Vínculo vencido sai do contexto."""
    raw = (
        await session.execute(text("select public.reconciliar_acessos_cliente()"))
    ).scalar_one()
    data = json.loads(raw) if isinstance(raw, str) else raw
    return {
        "eh_arquiteto": bool(data.get("eh_arquiteto")),
        "eh_cliente": bool(data.get("eh_cliente")),
        "tem_papel_cliente": bool(data.get("tem_papel_cliente")),
        "projetos": data.get("projetos") or [],
        "obras": data.get("obras") or [],
    }
