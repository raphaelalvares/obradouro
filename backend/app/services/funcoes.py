"""Serviço de Funções/cargos (Fatia C). ARQUITETO-ONLY via RLS self (tenant_id = auth.uid()) — a
biblioteca é do dono da conta. Espelha equipes (0065): CRUD simples, dedupe por nome_norm. Excluir
só DELETA (sem FK p/ o diário — o nome no efetivo é snapshot, então o histórico não é afetado).

`listar_da_obra` / `mapa_da_obra` usam a função SECURITY DEFINER funcoes_da_obra (0067): o PRESTADOR
que preenche o diário precisa LER a biblioteca do DONO da obra, que a RLS self bloquearia."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.funcoes import FuncaoCreate, FuncaoUpdate
from app.services.checklist_import import norm_nome
from app.services.common import obra_member

_COLS = "id, nome, ativo, created_at, updated_at"
_PATCH_COLS = ("nome", "ativo")


def _map_42501(e: DBAPIError) -> HTTPException | None:
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


async def listar(session: AsyncSession, incluir_inativos: bool = False) -> list[dict]:
    cond = "" if incluir_inativos else "and ativo = true"
    rows = (
        await session.execute(
            text(
                f"select {_COLS} from public.funcoes "
                f"where tenant_id = (select auth.uid()) {cond} order by nome"
            )
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def _get(session: AsyncSession, funcao_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(
                f"select {_COLS} from public.funcoes "
                "where id = cast(:i as uuid) and tenant_id = (select auth.uid())"
            ),
            {"i": str(funcao_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "função não encontrada")
    return dict(row._mapping)


async def criar(session: AsyncSession, user_id: str, data: FuncaoCreate) -> dict:
    nn = norm_nome(data.nome)
    if not nn:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "nome inválido")
    # idempotente por id (re-POST do mesmo uuid offline) → devolve o existente
    existing = (
        await session.execute(
            text(
                f"select {_COLS} from public.funcoes "
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
                    insert into public.funcoes (id, tenant_id, nome, nome_norm, created_by)
                    values (cast(:id as uuid), (select auth.uid()), :nome, :nn, (select auth.uid()))
                    """
                ),
                {"id": str(data.id), "nome": data.nome, "nn": nn},
            )
    except IntegrityError as e:
        # corrida na idempotência por id: 2º POST do MESMO uuid colide na PK → devolve o existente;
        # sem achar por id, foi colisão de (tenant, nome_norm) com OUTRO uuid → 409 de nome.
        found = (
            await session.execute(
                text(
                    f"select {_COLS} from public.funcoes "
                    "where id = cast(:i as uuid) and tenant_id = (select auth.uid())"
                ),
                {"i": str(data.id)},
            )
        ).first()
        if found is not None:
            return dict(found._mapping)
        raise HTTPException(
            status.HTTP_409_CONFLICT, "já existe uma função com esse nome"
        ) from e
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    return await _get(session, data.id)


async def atualizar(
    session: AsyncSession, user_id: str, funcao_id: uuid.UUID, data: FuncaoUpdate
) -> dict:
    await _get(session, funcao_id)  # 404 se não for do tenant
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if k in _PATCH_COLS}
    if not fields:
        return await _get(session, funcao_id)
    sets = [f"{k} = :{k}" for k in fields]
    params = dict(fields)
    if "nome" in fields:
        params["nn"] = norm_nome(fields["nome"])
        if not params["nn"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "nome inválido")
        sets.append("nome_norm = :nn")
    params["i"] = str(funcao_id)
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    f"update public.funcoes set {', '.join(sets)} "
                    "where id = cast(:i as uuid) and tenant_id = (select auth.uid())"
                ),
                params,
            )
    except IntegrityError as e:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "já existe uma função com esse nome"
        ) from e
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    return await _get(session, funcao_id)


async def excluir(session: AsyncSession, user_id: str, funcao_id: uuid.UUID) -> None:
    await _get(session, funcao_id)  # 404 se não for do tenant
    # sem checagem de uso: o efetivo do diário guarda um snapshot do nome (sem FK), então apagar a
    # função não mexe no histórico. Arquivar (ativo=false) some do picker, mas mantém p/ editar.
    try:
        await session.execute(
            text(
                "delete from public.funcoes "
                "where id = cast(:i as uuid) and tenant_id = (select auth.uid())"
            ),
            {"i": str(funcao_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e


# ============================ picker / validação por obra ============================
async def listar_da_obra(session: AsyncSession, obra_id: uuid.UUID) -> list[dict]:
    """Funções ATIVAS do tenant DONO da obra (picker do diário). Funciona p/ arquiteto E prestador
    (a função SECURITY DEFINER bypassa a RLS self e confere a participação na obra)."""
    await obra_member(session, obra_id)  # 403/404 limpos antes
    rows = (
        await session.execute(
            text("select id, nome from public.funcoes_da_obra(cast(:o as uuid))"),
            {"o": str(obra_id)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def mapa_da_obra(session: AsyncSession, obra_id: uuid.UUID) -> dict[str, str]:
    """{funcao_id: nome} de TODAS as funções (ativas + arquivadas) do tenant da obra — p/ VALIDAR o
    efetivo no salvar (editar entrada antiga que cita função já arquivada não pode quebrar)."""
    rows = (
        await session.execute(
            text("select id, nome from public.funcoes_da_obra(cast(:o as uuid), false)"),
            {"o": str(obra_id)},
        )
    ).all()
    return {str(r._mapping["id"]): r._mapping["nome"] for r in rows}
