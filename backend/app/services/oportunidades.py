"""Serviço do micro-CRM (Comercial): funil de oportunidades de venda.

Entidade TENANT-scoped (o funil é do arquiteto; sem membros). A RLS escopa SELECT/UPDATE/DELETE ao
dono (tenant = auth.uid); aqui validamos cedo p/ 404 limpo e auditamos. UUID vem do cliente
(offline/dual-ID); o seq_humano é do trigger. Conversão "ganho → obra" reusa a RPC criar_obra (cria
a obra + vínculo de arquiteto atomicamente; pode bater no limite do plano → soft-limit 403).
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problems import limite_from_exc
from app.schemas.oportunidades import (
    OportunidadeConverter,
    OportunidadeCreate,
    OportunidadeUpdate,
)
from app.services.audit import log_event
from app.services.common import actor_name

_COLS = (
    "id, nome, etapa, obra_id, contato_nome, contato_telefone, contato_email, origem, "
    "valor_estimado, proximo_followup, observacoes, seq_humano, created_at, updated_at"
)
# colunas editáveis no PATCH parcial → fragmento SQL (allowlist FIXA; nunca vem do usuário).
# bind direto, sem cast: em INSERT/UPDATE o tipo vem da coluna (date/numeric/text aceitam None).
_UPDATABLE = {
    "nome": "nome = :nome",
    "etapa": "etapa = :etapa",
    "contato_nome": "contato_nome = :contato_nome",
    "contato_telefone": "contato_telefone = :contato_telefone",
    "contato_email": "contato_email = :contato_email",
    "origem": "origem = :origem",
    "valor_estimado": "valor_estimado = :valor_estimado",
    "proximo_followup": "proximo_followup = :proximo_followup",
    "observacoes": "observacoes = :observacoes",
}
_OBRA_COLS = "id, nome, status, seq_humano, created_at"


def _map_42501(e: DBAPIError) -> HTTPException | None:
    """Guard do banco (camada 2) levanta 42501 → 403 limpo (não vazar como 500)."""
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


async def get_oportunidade(session: AsyncSession, op_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(f"select {_COLS} from public.oportunidades where id = cast(:id as uuid)"),
            {"id": str(op_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "oportunidade não encontrada")
    return dict(row._mapping)


async def list_oportunidades(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            text(
                f"select {_COLS} from public.oportunidades "
                "order by proximo_followup asc nulls last, created_at desc"
            )
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def create_oportunidade(
    session: AsyncSession, user_id: str, data: OportunidadeCreate
) -> dict:
    # idempotente (offline/retry): se o MESMO uuid já existe (dono), devolve sem re-auditar.
    existing = (
        await session.execute(
            text("select 1 from public.oportunidades where id = cast(:id as uuid)"),
            {"id": str(data.id)},
        )
    ).first()
    if existing is not None:
        return await get_oportunidade(session, data.id)

    params = {
        "id": str(data.id),
        "t": user_id,
        "nome": data.nome,
        "etapa": data.etapa,
        "contato_nome": data.contato_nome,
        "contato_telefone": data.contato_telefone,
        "contato_email": data.contato_email,
        "origem": data.origem,
        "valor_estimado": data.valor_estimado,
        "proximo_followup": data.proximo_followup,
        "observacoes": data.observacoes,
        "by": user_id,
    }
    try:
        row = (
            await session.execute(
                text(
                    f"""
                    insert into public.oportunidades
                      (id, tenant_id, nome, etapa, contato_nome, contato_telefone, contato_email,
                       origem, valor_estimado, proximo_followup, observacoes, created_by)
                    values
                      (cast(:id as uuid), cast(:t as uuid), :nome, :etapa, :contato_nome,
                       :contato_telefone, :contato_email, :origem, :valor_estimado,
                       :proximo_followup, :observacoes, cast(:by as uuid))
                    returning {_COLS}
                    """
                ),
                params,
            )
        ).first()
    except IntegrityError:
        return await get_oportunidade(session, data.id)
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e

    await log_event(
        session,
        tenant=user_id,
        actor_id=user_id,
        obra_id=None,
        action="oportunidade.criada",
        entity_type="oportunidade",
        entity_id=data.id,
        entity_label=row.nome,
        entity_seq=row.seq_humano,
        actor_label=await actor_name(session),
    )
    return dict(row._mapping)


async def update_oportunidade(
    session: AsyncSession, user_id: str, op_id: uuid.UUID, data: OportunidadeUpdate
) -> dict:
    cur = await get_oportunidade(session, op_id)  # 404 se não for do dono
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if k in _UPDATABLE}
    if fields.get("nome") is None:
        fields.pop("nome", None)  # nome é NOT NULL: ignora tentativa de limpar
    if not fields:
        return cur

    sets = ", ".join(_UPDATABLE[k] for k in fields)
    params = dict(fields)
    params["id"] = str(op_id)
    try:
        await session.execute(
            text(f"update public.oportunidades set {sets} where id = cast(:id as uuid)"), params
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e

    await log_event(
        session,
        tenant=user_id,
        actor_id=user_id,
        obra_id=None,
        action="oportunidade.atualizada",
        entity_type="oportunidade",
        entity_id=op_id,
        changed={k: (str(v) if v is not None else None) for k, v in fields.items()},
        entity_label=fields.get("nome") or cur["nome"],
        entity_seq=cur["seq_humano"],
        actor_label=await actor_name(session),
    )
    return await get_oportunidade(session, op_id)


async def delete_oportunidade(session: AsyncSession, user_id: str, op_id: uuid.UUID) -> dict:
    cur = await get_oportunidade(session, op_id)  # 404 se não for do dono
    await session.execute(
        text("delete from public.oportunidades where id = cast(:id as uuid)"), {"id": str(op_id)}
    )
    await log_event(
        session,
        tenant=user_id,
        actor_id=user_id,
        obra_id=None,
        action="oportunidade.excluida",
        entity_type="oportunidade",
        entity_id=op_id,
        entity_label=cur["nome"],
        entity_seq=cur["seq_humano"],
        actor_label=await actor_name(session),
    )
    return {"deleted": True}


async def converter(
    session: AsyncSession, user_id: str, op_id: uuid.UUID, data: OportunidadeConverter
) -> dict:
    """Cria uma OBRA a partir da oportunidade (ganho) e vincula. Reusa criar_obra (atômica)."""
    op = await get_oportunidade(session, op_id)  # 404 se não for do dono
    if op["obra_id"] is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "esta oportunidade já virou obra")
    try:
        obra = (
            await session.execute(
                text(f"select {_OBRA_COLS} from public.criar_obra(cast(:id as uuid), :nome)"),
                {"id": str(data.obra_id), "nome": op["nome"]},
            )
        ).first()
    except DBAPIError as e:
        err = limite_from_exc(e)  # P0001 'limite_obras_ativas:...' → soft-limit (403)
        if err is not None:
            raise err from e
        raise
    if obra is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "não foi possível criar a obra")

    try:
        await session.execute(
            text(
                "update public.oportunidades set obra_id = cast(:o as uuid), etapa = 'ganho' "
                "where id = cast(:id as uuid)"
            ),
            {"o": str(data.obra_id), "id": str(op_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e

    nome_ator = await actor_name(session)
    await log_event(
        session,
        tenant=user_id,
        actor_id=user_id,
        obra_id=data.obra_id,
        action="obra.criada",
        entity_type="obra",
        entity_id=data.obra_id,
        entity_label=obra.nome,
        entity_seq=obra.seq_humano,
        actor_label=nome_ator,
    )
    await log_event(
        session,
        tenant=user_id,
        actor_id=user_id,
        obra_id=data.obra_id,
        action="oportunidade.convertida",
        entity_type="oportunidade",
        entity_id=op_id,
        changed={"obra_id": str(data.obra_id)},
        entity_label=op["nome"],
        entity_seq=op["seq_humano"],
        actor_label=nome_ator,
    )
    return dict(obra._mapping)
