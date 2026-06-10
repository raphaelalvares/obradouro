"""Ambientes (cômodos) — registro por obra + pivot por ambiente (Fatia A · parte 1).

ADITIVO ao `checklist_itens.ambiente` (texto): o registro dá identidade (id/ordem/área) e o texto
segue como nome denormalizado p/ display/PDF/CSV. O registro é AUTO-MANTIDO a partir do texto:
`resolver()` faz resolve-or-create por nome_norm; `atualizar_detalhes` (checklist) e `reconciliar`
(pós-import) chamam isso. NORM simples (minúsculo+trim+colapsa-espaços, SEM tirar acento) — idêntico
ao backfill SQL da 0062 (evita a dependência da extensão unaccent). Autorização: arquiteto-only.
"""

import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.checklist import AmbienteCreate, AmbienteUpdate
from app.services.audit import log_event
from app.services.common import actor_name, obra_writable

_SELECT = "select id, nome, ordem, area_m2 from public.ambientes"


def _limpo(nome: str) -> str:
    """Nome de exibição normalizado: colapsa whitespace ASCII + trim. Classe ASCII EXPLÍCITA
    [ \\t\\n\\r\\f\\v] (NÃO \\s) p/ casar byte-a-byte com o backfill SQL da 0062 — o \\s do Postgres
    depende de locale (NBSP etc.); o ASCII fixo é determinístico nos dois lados."""
    return re.sub(r"[ \t\n\r\f\v]+", " ", nome or "").strip()


def _norm(nome: str) -> str:
    """Chave de dedupe do ambiente: _limpo + minúsculo. SEM tirar acento (≠ norm_nome; casa com o
    backfill SQL da 0062)."""
    return _limpo(nome).lower()


def _map_42501(e: DBAPIError) -> HTTPException | None:
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta alteração")
    return None


async def listar(session: AsyncSession, obra_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            text(f"{_SELECT} where obra_id = cast(:o as uuid) order by ordem, created_at"),
            {"o": str(obra_id)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def resolver(
    session: AsyncSession, obra_id: uuid.UUID, tenant_id, nome: str
) -> tuple[uuid.UUID, str]:
    """Resolve-or-create do ambiente por nome_norm. Devolve (id, nome_canônico do registro). Assume
    que o chamador já autorizou (obra_writable); o INSERT ainda passa pelo guard como backstop."""
    limpo = _limpo(nome)
    nn = limpo.lower()
    found = (
        await session.execute(
            text(
                "select id, nome from public.ambientes "
                "where obra_id = cast(:o as uuid) and nome_norm = :nn"
            ),
            {"o": str(obra_id), "nn": nn},
        )
    ).first()
    if found is not None:
        return found.id, found.nome
    novo = uuid.uuid4()
    try:
        async with session.begin_nested():  # savepoint: corrida não polui a txn
            await session.execute(
                text(
                    """
                    insert into public.ambientes (id, obra_id, tenant_id, nome, nome_norm, ordem)
                    values (cast(:id as uuid), cast(:o as uuid), cast(:t as uuid), :nome, :nn,
                            (select coalesce(max(ordem), -1) + 1 from public.ambientes
                             where obra_id = cast(:o as uuid)))
                    """
                ),
                {"id": str(novo), "o": str(obra_id), "t": str(tenant_id), "nome": limpo, "nn": nn},
            )
        return novo, limpo
    except IntegrityError:  # corrida: outra txn criou o mesmo nome_norm → re-seleciona
        row = (
            await session.execute(
                text(
                    "select id, nome from public.ambientes "
                    "where obra_id = cast(:o as uuid) and nome_norm = :nn"
                ),
                {"o": str(obra_id), "nn": nn},
            )
        ).first()
        if row is None:  # DELETE concorrente removeu no intervalo → reentra resolve-or-create
            return await resolver(session, obra_id, tenant_id, nome)
        return row.id, row.nome


async def criar(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, data: AmbienteCreate
) -> dict:
    cur = await obra_writable(session, obra_id)  # camada 1: só arquiteto
    # idempotente por id (re-POST do mesmo uuid) → devolve o existente
    existing = (
        await session.execute(
            text(f"{_SELECT} where id = cast(:id as uuid) and obra_id = cast(:o as uuid)"),
            {"id": str(data.id), "o": str(obra_id)},
        )
    ).first()
    if existing is not None:
        return dict(existing._mapping)
    limpo = _limpo(data.nome)
    nn = limpo.lower()
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    insert into public.ambientes
                      (id, obra_id, tenant_id, nome, nome_norm, ordem, area_m2, created_by)
                    values (cast(:id as uuid), cast(:o as uuid), cast(:t as uuid), :nome, :nn,
                            (select coalesce(max(ordem), -1) + 1 from public.ambientes
                             where obra_id = cast(:o as uuid)),
                            :area, cast(:uid as uuid))
                    """
                ),
                {
                    "id": str(data.id),
                    "o": str(obra_id),
                    "t": str(cur.tenant_id),
                    "nome": limpo,
                    "nn": nn,
                    "area": data.area_m2,
                    "uid": str(user_id),
                },
            )
    except IntegrityError:  # nome já existe (outro uuid) → MERGE: devolve o existente
        row = (
            await session.execute(
                text(f"{_SELECT} where obra_id = cast(:o as uuid) and nome_norm = :nn"),
                {"o": str(obra_id), "nn": nn},
            )
        ).first()
        if row is None:  # corrida: o conflitante foi removido entre o INSERT e o re-select
            raise HTTPException(status.HTTP_409_CONFLICT, "conflito ao criar ambiente") from None
        return dict(row._mapping)
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    row = (
        await session.execute(text(f"{_SELECT} where id = cast(:id as uuid)"), {"id": str(data.id)})
    ).first()
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="ambiente.criado",
        entity_type="ambiente",
        entity_id=data.id,
        entity_label=limpo,
        actor_label=await actor_name(session),
    )
    return dict(row._mapping)


async def atualizar(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, amb_id: uuid.UUID, data: AmbienteUpdate
) -> dict:
    cur = await obra_writable(session, obra_id)
    campos = data.model_dump(exclude_unset=True)
    prev = (
        await session.execute(
            text(
                "select nome from public.ambientes "
                "where id = cast(:a as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"a": str(amb_id), "o": str(obra_id)},
        )
    ).first()
    if prev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ambiente não encontrado")
    sets, params = [], {"a": str(amb_id), "o": str(obra_id)}
    novo_nome = None
    if "nome" in campos and campos["nome"]:
        novo_nome = _limpo(campos["nome"])
        sets += ["nome = :nome", "nome_norm = :nn"]
        params["nome"] = novo_nome
        params["nn"] = novo_nome.lower()
    if "area_m2" in campos:  # None aqui = limpar a área
        sets.append("area_m2 = :area")
        params["area"] = campos["area_m2"]
    if not sets:
        row = (
            await session.execute(
                text(f"{_SELECT} where id = cast(:a as uuid)"), {"a": str(amb_id)}
            )
        ).first()
        return dict(row._mapping)
    try:
        await session.execute(
            text(
                f"update public.ambientes set {', '.join(sets)} "
                "where id = cast(:a as uuid) and obra_id = cast(:o as uuid)"
            ),
            params,
        )
    except IntegrityError as e:  # rename colidiu com outro ambiente da obra
        raise HTTPException(status.HTTP_409_CONFLICT, "já existe um ambiente com esse nome") from e
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    # rename: propaga o nome denormalizado p/ os itens ligados (display/PDF/CSV seguem o registro)
    if novo_nome is not None:
        await session.execute(
            text(
                "update public.checklist_itens set ambiente = :nome "
                "where ambiente_id = cast(:a as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"nome": novo_nome, "a": str(amb_id), "o": str(obra_id)},
        )
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="ambiente.atualizado",
        entity_type="ambiente",
        entity_id=amb_id,
        changed=campos,
        entity_label=novo_nome or prev.nome,
        actor_label=await actor_name(session),
    )
    row = (
        await session.execute(text(f"{_SELECT} where id = cast(:a as uuid)"), {"a": str(amb_id)})
    ).first()
    return dict(row._mapping)


async def excluir(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, amb_id: uuid.UUID
) -> dict:
    cur = await obra_writable(session, obra_id)
    prev = (
        await session.execute(
            text(
                "select nome from public.ambientes "
                "where id = cast(:a as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"a": str(amb_id), "o": str(obra_id)},
        )
    ).first()
    if prev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ambiente não encontrado")
    # desliga o cômodo dos itens (id E texto) — o FK faria só o id; o texto ficaria órfão
    try:
        await session.execute(
            text(
                "update public.checklist_itens set ambiente = null, ambiente_id = null "
                "where ambiente_id = cast(:a as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"a": str(amb_id), "o": str(obra_id)},
        )
        await session.execute(
            text("delete from public.ambientes where id = cast(:a as uuid)"), {"a": str(amb_id)}
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="ambiente.removido",
        entity_type="ambiente",
        entity_id=amb_id,
        entity_label=prev.nome,
        actor_label=await actor_name(session),
    )
    return {"deleted": True}


async def reordenar(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, ids: list[uuid.UUID]
) -> list[dict]:
    await obra_writable(session, obra_id)  # camada 1: só arquiteto (sem audit — proporcionalidade)
    try:
        for idx, aid in enumerate(ids):
            await session.execute(
                text(
                    "update public.ambientes set ordem = :ord "
                    "where id = cast(:a as uuid) and obra_id = cast(:o as uuid)"
                ),
                {"ord": idx, "a": str(aid), "o": str(obra_id)},
            )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    return await listar(session, obra_id)


async def reconciliar(session: AsyncSession, obra_id: uuid.UUID, tenant_id) -> None:
    """Liga itens com `ambiente` (texto) mas ainda sem `ambiente_id` (ex.: vindos do import RPC):
    resolve-or-create por nome e canoniza o texto. Assume autorização já feita pelo chamador."""
    pend = (
        await session.execute(
            text(
                "select id, ambiente from public.checklist_itens where obra_id = cast(:o as uuid) "
                "and ambiente_id is null and ambiente is not null and btrim(ambiente) <> ''"
            ),
            {"o": str(obra_id)},
        )
    ).all()
    cache: dict[str, tuple[uuid.UUID, str]] = {}
    for r in pend:
        nn = _norm(r.ambiente)
        if not nn:
            continue
        if nn not in cache:
            cache[nn] = await resolver(session, obra_id, tenant_id, r.ambiente)
        aid, canonical = cache[nn]
        await session.execute(
            text(
                "update public.checklist_itens "
                "set ambiente_id = cast(:a as uuid), ambiente = :nome where id = cast(:i as uuid)"
            ),
            {"a": str(aid), "nome": canonical, "i": str(r.id)},
        )
