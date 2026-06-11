"""Serviço de Equipes (Fatia A · parte 2). ARQUITETO-ONLY via RLS self (tenant_id = auth.uid()) — a
biblioteca de equipes é do dono da conta; membros de obra não a acessam. Espelha o catálogo (0063):
CRUD simples, dedupe por nome_norm. Excluir só DELETA — o FK `on delete set null` desliga a equipe
das tarefas (em qualquer obra) sem apagá-las."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.equipes import EquipeCreate, EquipeUpdate
from app.services.checklist_import import norm_nome

_COLS = "id, nome, cor, contato, ativo, created_at, updated_at"
_PATCH_COLS = ("nome", "cor", "contato", "ativo")


def _map_42501(e: DBAPIError) -> HTTPException | None:
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


async def listar(session: AsyncSession, incluir_inativos: bool = False) -> list[dict]:
    cond = "" if incluir_inativos else "and ativo = true"
    rows = (
        await session.execute(
            text(
                f"select {_COLS} from public.equipes "
                f"where tenant_id = (select auth.uid()) {cond} order by nome"
            )
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def _get(session: AsyncSession, equipe_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(
                f"select {_COLS} from public.equipes "
                "where id = cast(:i as uuid) and tenant_id = (select auth.uid())"
            ),
            {"i": str(equipe_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "equipe não encontrada")
    return dict(row._mapping)


async def criar(session: AsyncSession, user_id: str, data: EquipeCreate) -> dict:
    nn = norm_nome(data.nome)
    if not nn:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "nome inválido")
    # idempotente por id (re-POST do mesmo uuid offline) → devolve o existente
    existing = (
        await session.execute(
            text(
                f"select {_COLS} from public.equipes "
                "where id = cast(:i as uuid) and tenant_id = (select auth.uid())"
            ),
            {"i": str(data.id)},
        )
    ).first()
    if existing is not None:
        return dict(existing._mapping)
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    insert into public.equipes
                      (id, tenant_id, nome, nome_norm, cor, contato, created_by)
                    values (cast(:id as uuid), (select auth.uid()), :nome, :nn, :cor, :contato,
                            (select auth.uid()))
                    """
                ),
                {
                    "id": str(data.id), "nome": data.nome, "nn": nn,
                    "cor": data.cor, "contato": data.contato,
                },
            )
    except IntegrityError as e:
        # corrida na idempotência por id: dois POSTs do MESMO uuid passam o pré-check e o 2º colide
        # na PK → re-seleciona por id e devolve o existente (em vez de 409 de nome). Sem achar por
        # id, foi colisão de (tenant, nome_norm) com OUTRO uuid → 409 de nome.
        found = (
            await session.execute(
                text(
                    f"select {_COLS} from public.equipes "
                    "where id = cast(:i as uuid) and tenant_id = (select auth.uid())"
                ),
                {"i": str(data.id)},
            )
        ).first()
        if found is not None:
            return dict(found._mapping)
        raise HTTPException(
            status.HTTP_409_CONFLICT, "já existe uma equipe com esse nome"
        ) from e
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    return await _get(session, data.id)


async def atualizar(
    session: AsyncSession, user_id: str, equipe_id: uuid.UUID, data: EquipeUpdate
) -> dict:
    await _get(session, equipe_id)  # 404 se não for do tenant
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if k in _PATCH_COLS}
    # cor é NOT NULL no banco: `{"cor": null}` explícito (cliente malformado) viraria `cor = NULL`
    # → IntegrityError 409 enganoso. Trata null como "não mexer" (descarta de fields).
    if fields.get("cor") is None:
        fields.pop("cor", None)
    if not fields:
        return await _get(session, equipe_id)
    sets = [f"{k} = :{k}" for k in fields]
    params = dict(fields)
    if "nome" in fields:
        params["nn"] = norm_nome(fields["nome"])
        if not params["nn"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "nome inválido")
        sets.append("nome_norm = :nn")
    params["i"] = str(equipe_id)
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    f"update public.equipes set {', '.join(sets)} "
                    "where id = cast(:i as uuid) and tenant_id = (select auth.uid())"
                ),
                params,
            )
    except IntegrityError as e:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "já existe uma equipe com esse nome"
        ) from e
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    return await _get(session, equipe_id)


async def excluir(session: AsyncSession, user_id: str, equipe_id: uuid.UUID) -> None:
    await _get(session, equipe_id)  # 404 se não for do tenant
    # sem checagem de uso: o FK `on delete set null` desliga a equipe das tarefas (em qualquer obra)
    # sem apagá-las — comportamento idêntico ao "excluir cômodo" (0062). Histórico fica no audit.
    try:
        await session.execute(
            text(
                "delete from public.equipes "
                "where id = cast(:i as uuid) and tenant_id = (select auth.uid())"
            ),
            {"i": str(equipe_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
