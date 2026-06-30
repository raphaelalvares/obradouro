"""Serviço de projetos (Módulo de Projeto, Fase 5).

Criação via RPC SECURITY DEFINER `criar_projeto` (criador vira arquiteto/ativo atomicamente,
idempotente sem queimar seq). O limite de alterações (`revisoes_incluidas`) é parâmetro do ARQUITETO
por projeto — definido no onboarding via UPDATE (não é eixo de plano). Audit CORE com projeto_id.
"""

import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.projetos import ProjetoCreate, ProjetoUpdate
from app.services.audit import log_event
from app.services.common import actor_name, projeto_writable

# meu_papel = papel do usuário corrente (subquery correlacionada): o front gateia a UI com ele.
_PROJ_COLS = """
    id, nome, obra_id, briefing, revisoes_incluidas, seq_humano, created_at,
    (select pm.papel from public.projeto_membros pm
      where pm.projeto_id = projetos.id
        and pm.profile_id = (select auth.uid())
        and pm.estado = 'ativo') as meu_papel
"""


def _map_42501(e: DBAPIError) -> HTTPException | None:
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


def _row_to_out(row) -> dict:
    d = dict(row._mapping)
    if isinstance(d.get("briefing"), str):  # asyncpg devolve jsonb como texto
        d["briefing"] = json.loads(d["briefing"])
    return d


async def get_projeto(session: AsyncSession, projeto_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(f"select {_PROJ_COLS} from public.projetos where id = cast(:id as uuid)"),
            {"id": str(projeto_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "projeto não encontrado")
    return _row_to_out(row)


async def list_projetos(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            text(f"select {_PROJ_COLS} from public.projetos order by seq_humano")
        )
    ).all()
    return [_row_to_out(r) for r in rows]


async def create_projeto(session: AsyncSession, user_id: str, data: ProjetoCreate) -> dict:
    try:
        row = (
            await session.execute(
                text(
                    """
                    select id, nome, obra_id, seq_humano, created_at
                    from public.criar_projeto(cast(:id as uuid), :nome, cast(:brief as jsonb))
                    """
                ),
                {"id": str(data.id), "nome": data.nome, "brief": json.dumps(data.briefing or {})},
            )
        ).first()
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "não foi possível criar o projeto")

    # o arquiteto define as alterações incluídas (onboarding). Update à parte (RPC não recebe).
    if data.revisoes_incluidas is not None:
        await session.execute(
            text(
                "update public.projetos set revisoes_incluidas = :r where id = cast(:id as uuid)"
            ),
            {"r": data.revisoes_incluidas, "id": str(data.id)},
        )

    # semeia a linha do tempo (9 etapas fixas) — pipeline do projeto (0097)
    await session.execute(
        text("select public.garantir_etapas_projeto(cast(:id as uuid))"),
        {"id": str(data.id)},
    )

    await log_event(
        session,
        tenant=user_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=data.id,
        action="projeto.criado",
        entity_type="projeto",
        entity_id=data.id,
        changed={"revisoes_incluidas": data.revisoes_incluidas},
        entity_label=row.nome,
        entity_seq=row.seq_humano,
        actor_label=await actor_name(session),
    )
    return await get_projeto(session, data.id)


async def update_projeto(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, data: ProjetoUpdate
) -> dict:
    cur = await projeto_writable(session, projeto_id)  # só arquiteto
    sets, params = [], {"id": str(projeto_id)}
    if data.nome is not None:
        sets.append("nome = :nome")
        params["nome"] = data.nome
    if data.briefing is not None:
        sets.append("briefing = cast(:brief as jsonb)")
        params["brief"] = json.dumps(data.briefing)
    if data.revisoes_incluidas is not None:
        sets.append("revisoes_incluidas = :rev")
        params["rev"] = data.revisoes_incluidas
    if not sets:
        return await get_projeto(session, projeto_id)
    try:
        await session.execute(
            text(f"update public.projetos set {', '.join(sets)} where id = cast(:id as uuid)"),
            params,
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="projeto.atualizado",
        entity_type="projeto",
        entity_id=projeto_id,
        changed={k: v for k, v in params.items() if k != "id"},
        entity_label=data.nome or cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return await get_projeto(session, projeto_id)


async def vincular_obra(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, obra_id: uuid.UUID | None
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    if obra_id is not None:
        # camada 1: a obra tem de ser do MESMO tenant (erro limpo antes do guard 0040)
        own = (
            await session.execute(
                text(
                    "select 1 from public.obras o "
                    "where o.id = cast(:oid as uuid) and o.tenant_id = cast(:t as uuid)"
                ),
                {"oid": str(obra_id), "t": str(cur.tenant_id)},
            )
        ).first()
        if own is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "obra não encontrada no seu acervo"
            )
    try:
        await session.execute(
            text("update public.projetos set obra_id = :oid where id = cast(:id as uuid)"),
            {"oid": str(obra_id) if obra_id else None, "id": str(projeto_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        projeto_id=projeto_id,
        action="projeto.obra_vinculada" if obra_id else "projeto.obra_desvinculada",
        entity_type="projeto",
        entity_id=projeto_id,
        changed={"obra_id": str(obra_id) if obra_id else None},
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return await get_projeto(session, projeto_id)


async def list_audit(
    session: AsyncSession, projeto_id: uuid.UUID, *, limit: int = 100, offset: int = 0
) -> list[dict]:
    # I6: paginado (mais recentes primeiro) — corta o crescimento ilimitado da resposta.
    rows = (
        await session.execute(
            text(
                """
                select id, action, entity_type, entity_id, entity_label, entity_seq,
                       actor_label, changed, created_at
                from public.audit_log
                where projeto_id = cast(:id as uuid)
                order by created_at desc
                limit :lim offset :off
                """
            ),
            {"id": str(projeto_id), "lim": limit, "off": offset},
        )
    ).all()
    out = []
    for r in rows:
        d = dict(r._mapping)
        if isinstance(d.get("changed"), str):
            d["changed"] = json.loads(d["changed"])
        out.append(d)
    return out
