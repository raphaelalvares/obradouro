"""Pendências / punch list (Fatia C). Defeitos/itens a resolver na obra. Quem EXECUTA (arquiteto OU
prestador) abre e resolve; cliente lê. Arquiteto edita tudo; prestador SÓ resolve/reabre (allowlist
no guard 0066). ambiente_id (onde, mesma obra) e equipe_id (responsável, tenant) opcionais. Fotos
via anexos (parent_type='pendencia')."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.acompanhamento import PendenciaCreate, PendenciaUpdate
from app.services.audit import log_event
from app.services.common import actor_name, obra_executor, obra_member

_SELECT = """
    select pe.id, pe.descricao, pe.ambiente_id, pe.equipe_id, pe.prioridade, pe.status,
           pe.resolvido_por, pe.resolvido_em, pe.seq_humano, pe.created_by,
           pe.created_at, pe.updated_at,
           autor.nome as autor_nome, resolv.nome as resolvido_por_nome,
           (select count(*) from public.anexos a
            where a.parent_type = 'pendencia' and a.parent_id = pe.id) as n_fotos
    from public.pendencias pe
    left join public.profiles autor  on autor.id  = pe.created_by
    left join public.profiles resolv on resolv.id = pe.resolvido_por
"""
_TEXT_COLS = ("descricao", "prioridade", "status")
_UUID_COLS = ("ambiente_id", "equipe_id")


def _map_42501(e: DBAPIError) -> HTTPException | None:
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta alteração")
    return None


async def _valida_refs(
    session: AsyncSession, obra_id: uuid.UUID, tenant_id, ambiente_id, equipe_id
) -> None:
    """ambiente é desta obra; equipe é do mesmo tenant (dono da obra). 404 limpo antes do guard."""
    if ambiente_id is not None:
        ok = (
            await session.execute(
                text(
                    "select 1 from public.ambientes "
                    "where id = cast(:a as uuid) and obra_id = cast(:o as uuid)"
                ),
                {"a": str(ambiente_id), "o": str(obra_id)},
            )
        ).first()
        if ok is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "cômodo não encontrado nesta obra")
    if equipe_id is not None:
        ok = (
            await session.execute(
                text(
                    "select 1 from public.equipes "
                    "where id = cast(:e as uuid) and tenant_id = cast(:t as uuid)"
                ),
                {"e": str(equipe_id), "t": str(tenant_id)},
            )
        ).first()
        if ok is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "equipe não encontrada")


async def _get(session: AsyncSession, obra_id: uuid.UUID, pend_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(f"{_SELECT} where pe.id = cast(:i as uuid) and pe.obra_id = cast(:o as uuid)"),
            {"i": str(pend_id), "o": str(obra_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "pendência não encontrada")
    return dict(row._mapping)


async def listar(
    session: AsyncSession, obra_id: uuid.UUID, status_filtro: str | None = None
) -> list[dict]:
    await obra_member(session, obra_id)  # qualquer membro ativo vê o punch list
    cond, params = "", {"o": str(obra_id)}
    if status_filtro in ("aberta", "resolvida"):
        cond = "and pe.status = :st"
        params["st"] = status_filtro
    rows = (
        await session.execute(
            text(
                f"{_SELECT} where pe.obra_id = cast(:o as uuid) {cond} "
                # abertas primeiro; depois prioridade alta→baixa; mais recentes no topo
                "order by (pe.status = 'resolvida'), "
                "array_position(array['alta','media','baixa'], pe.prioridade), pe.created_at desc"
            ),
            params,
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def criar(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, data: PendenciaCreate
) -> dict:
    cur = await obra_executor(session, obra_id)  # arquiteto OU prestador
    # idempotente por id, escopado por obra (PK GLOBAL); id de outra obra cai no INSERT → 23505.
    existing = (
        await session.execute(
            text(
                "select 1 from public.pendencias "
                "where id = cast(:i as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"i": str(data.id), "o": str(obra_id)},
        )
    ).first()
    if existing is not None:
        return await _get(session, obra_id, data.id)
    await _valida_refs(session, obra_id, cur.tenant_id, data.ambiente_id, data.equipe_id)
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    insert into public.pendencias
                      (id, obra_id, tenant_id, descricao, ambiente_id, equipe_id, prioridade,
                       created_by)
                    values (cast(:id as uuid), cast(:o as uuid), cast(:t as uuid), :descricao,
                            cast(:amb as uuid), cast(:eq as uuid), :prioridade, (select auth.uid()))
                    """
                ),
                {
                    "id": str(data.id), "o": str(obra_id), "t": str(cur.tenant_id),
                    "descricao": data.descricao,
                    "amb": str(data.ambiente_id) if data.ambiente_id else None,
                    "eq": str(data.equipe_id) if data.equipe_id else None,
                    "prioridade": data.prioridade,
                },
            )
    except IntegrityError as e:
        # corrida no MESMO id → devolve o existente da obra; id de OUTRA obra (PK global) → 409.
        existe = (
            await session.execute(
                text(
                    "select 1 from public.pendencias "
                    "where id = cast(:i as uuid) and obra_id = cast(:o as uuid)"
                ),
                {"i": str(data.id), "o": str(obra_id)},
            )
        ).first()
        if existe is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "id já utilizado") from e
        return await _get(session, obra_id, data.id)
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    row = await _get(session, obra_id, data.id)
    await log_event(
        session, tenant=cur.tenant_id, actor_id=user_id, obra_id=obra_id, action="pendencia.criada",
        entity_type="pendencia", entity_id=data.id, entity_label=data.descricao[:120],
        entity_seq=row["seq_humano"], actor_label=await actor_name(session),
    )
    return row


async def atualizar(
    session: AsyncSession,
    user_id: str,
    obra_id: uuid.UUID,
    pend_id: uuid.UUID,
    data: PendenciaUpdate,
) -> dict:
    cur = await obra_executor(session, obra_id)  # guard reforça allowlist do prestador
    prev = await _get(session, obra_id, pend_id)
    dump = data.model_dump(exclude_unset=True)
    fields = {k: v for k, v in dump.items() if k in _TEXT_COLS or k in _UUID_COLS}
    if not fields:
        return prev
    if "ambiente_id" in fields or "equipe_id" in fields:
        await _valida_refs(
            session, obra_id, cur.tenant_id,
            fields.get("ambiente_id", prev["ambiente_id"]) if "ambiente_id" in fields else None,
            fields.get("equipe_id", prev["equipe_id"]) if "equipe_id" in fields else None,
        )
    sets, params = [], {"i": str(pend_id), "o": str(obra_id)}
    for k, val in fields.items():
        if k in _UUID_COLS:
            sets.append(f"{k} = cast(:{k} as uuid)")
            params[k] = str(val) if val else None
        else:
            sets.append(f"{k} = :{k}")
            params[k] = val
    # mudar o status carimba/limpa o "resolvido por/em" (o prestador só chega aqui via allowlist).
    if "status" in fields:
        if fields["status"] == "resolvida":
            sets += ["resolvido_por = (select auth.uid())", "resolvido_em = now()"]
        else:
            sets += ["resolvido_por = null", "resolvido_em = null"]
    try:
        await session.execute(
            text(
                f"update public.pendencias set {', '.join(sets)} "
                "where id = cast(:i as uuid) and obra_id = cast(:o as uuid)"
            ),
            params,
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    acao = "pendencia.resolvida" if fields.get("status") == "resolvida" else "pendencia.editada"
    await log_event(
        session, tenant=cur.tenant_id, actor_id=user_id, obra_id=obra_id, action=acao,
        entity_type="pendencia", entity_id=pend_id, changed=fields,
        entity_label=prev["descricao"][:120], entity_seq=prev["seq_humano"],
        actor_label=await actor_name(session),
    )
    return await _get(session, obra_id, pend_id)


async def excluir(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, pend_id: uuid.UUID
) -> dict:
    cur = await obra_executor(session, obra_id)  # guard reforça "prestador só a própria"
    prev = await _get(session, obra_id, pend_id)
    try:
        await session.execute(
            text(
                "delete from public.pendencias "
                "where id = cast(:i as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"i": str(pend_id), "o": str(obra_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session, tenant=cur.tenant_id, actor_id=user_id, obra_id=obra_id,
        action="pendencia.removida",
        entity_type="pendencia", entity_id=pend_id, entity_label=prev["descricao"][:120],
        entity_seq=prev["seq_humano"], actor_label=await actor_name(session),
    )
    return {"deleted": True}
