"""Serviço do micro-CRM (Comercial): funil de oportunidades de venda.

Entidade TENANT-scoped (o funil é do arquiteto; sem membros). A RLS escopa SELECT/UPDATE/DELETE ao
dono (tenant = auth.uid); aqui validamos cedo p/ 404 limpo e auditamos. UUID vem do cliente
(offline/dual-ID); o seq_humano é do trigger. Conversão "ganho → obra" reusa a RPC criar_obra (cria
a obra + vínculo de arquiteto atomicamente; pode bater no limite do plano → soft-limit 403).
"""

import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.problems import limite_from_exc
from app.schemas.oportunidades import (
    ComentarioCreate,
    ComentarioUpdate,
    OportunidadeConverter,
    OportunidadeCreate,
    OportunidadeCriarProjeto,
    OportunidadeUpdate,
    OportunidadeVincularProjeto,
)
from app.services import projetos as proj_svc
from app.services.audit import log_event
from app.services.common import actor_name

_COLS = (
    "id, nome, etapa, etapa_obra, obra_id, projeto_id, contato_nome, contato_telefone, "
    "contato_email, origem, valor_estimado, valor_obra, proximo_followup, observacoes, "
    "(select count(*) from public.oportunidade_comentarios c "
    "where c.oportunidade_id = oportunidades.id) as comentarios_count, "
    "seq_humano, created_at, updated_at"
)
# colunas editáveis no PATCH parcial → fragmento SQL (allowlist FIXA; nunca vem do usuário).
# bind direto, sem cast: em INSERT/UPDATE o tipo vem da coluna (date/numeric/text aceitam None).
_UPDATABLE = {
    "nome": "nome = :nome",
    "etapa": "etapa = :etapa",
    "etapa_obra": "etapa_obra = :etapa_obra",
    "contato_nome": "contato_nome = :contato_nome",
    "contato_telefone": "contato_telefone = :contato_telefone",
    "contato_email": "contato_email = :contato_email",
    "origem": "origem = :origem",
    "valor_estimado": "valor_estimado = :valor_estimado",
    "valor_obra": "valor_obra = :valor_obra",
    "proximo_followup": "proximo_followup = :proximo_followup",
    "observacoes": "observacoes = :observacoes",
}
_OBRA_COLS = "id, nome, status, seq_humano, created_at"


def aplicar_auto_abrir_obra(fields: dict, etapa_obra_atual: str | None) -> dict:
    """Poka-yoke (pura/testável): ganhar o PROJETO (etapa='ganho') ABRE o funil de obra em 'a_orcar'
    quando o card ainda não está nele. Não recua nem sobrescreve quem já está em obra.
    """
    if (
        fields.get("etapa") == "ganho"
        and "etapa_obra" not in fields
        and etapa_obra_atual is None
    ):
        return {**fields, "etapa_obra": "a_orcar"}
    return fields


def _map_42501(e: DBAPIError) -> HTTPException | None:
    """Guard do banco (camada 2) levanta 42501 → 403 limpo (não vazar como 500)."""
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


def _map_conflito_projeto(e: DBAPIError) -> HTTPException | None:
    """Violação do índice 1:1 oportunidade↔projeto (23505) → 409 limpo (anti-corrida)."""
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "23505":
        return HTTPException(
            status.HTTP_409_CONFLICT, "este projeto já está vinculado a outra oportunidade"
        )
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
        "etapa_obra": data.etapa_obra,
        "contato_nome": data.contato_nome,
        "contato_telefone": data.contato_telefone,
        "contato_email": data.contato_email,
        "origem": data.origem,
        "valor_estimado": data.valor_estimado,
        "valor_obra": data.valor_obra,
        "proximo_followup": data.proximo_followup,
        "observacoes": data.observacoes,
        "by": user_id,
    }
    try:
        async with session.begin_nested():  # savepoint: erro reverte só o INSERT, txn segue usável
            row = (
                await session.execute(
                    text(
                        """
                        insert into public.oportunidades
                          (id, tenant_id, nome, etapa, etapa_obra, contato_nome, contato_telefone,
                           contato_email, origem, valor_estimado, valor_obra, proximo_followup,
                           observacoes, created_by)
                        values
                          (cast(:id as uuid), cast(:t as uuid), :nome, :etapa, :etapa_obra,
                           :contato_nome, :contato_telefone, :contato_email, :origem,
                           :valor_estimado, :valor_obra, :proximo_followup, :observacoes,
                           cast(:by as uuid))
                        returning nome, seq_humano
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
    return await get_oportunidade(session, data.id)


async def update_oportunidade(
    session: AsyncSession, user_id: str, op_id: uuid.UUID, data: OportunidadeUpdate
) -> dict:
    cur = await get_oportunidade(session, op_id)  # 404 se não for do dono
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if k in _UPDATABLE}
    if fields.get("nome") is None:
        fields.pop("nome", None)  # nome é NOT NULL: ignora tentativa de limpar
    fields = aplicar_auto_abrir_obra(fields, cur.get("etapa_obra"))  # ganhar projeto → abre obra
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
        # a conversão é a vitória da OBRA: fecha o funil de obra (etapa_obra='ganho') + liga a obra.
        # O funil de projeto fica como está — ganhar o projeto não é perda.
        await session.execute(
            text(
                "update public.oportunidades set obra_id = cast(:o as uuid), etapa_obra = 'ganho' "
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

    # fecha a cadeia lead → projeto → obra: se já há projeto vinculado (e ele ainda não tem obra),
    # amarra o projeto à obra recém-criada. (guard de projetos exige obra do MESMO tenant.)
    if op["projeto_id"] is not None:
        try:
            linked = (
                await session.execute(
                    text(
                        "update public.projetos set obra_id = cast(:o as uuid) "
                        "where id = cast(:p as uuid) and obra_id is null returning seq_humano, nome"
                    ),
                    {"o": str(data.obra_id), "p": str(op["projeto_id"])},
                )
            ).first()
        except DBAPIError as e:
            raise (_map_42501(e) or e) from e
        if linked is not None:
            await log_event(
                session,
                tenant=user_id,
                actor_id=user_id,
                obra_id=data.obra_id,
                projeto_id=op["projeto_id"],
                action="projeto.obra_vinculada",
                entity_type="projeto",
                entity_id=op["projeto_id"],
                changed={"obra_id": str(data.obra_id)},
                entity_label=linked.nome,
                entity_seq=linked.seq_humano,
                actor_label=nome_ator,
            )
    return dict(obra._mapping)


async def criar_projeto_da_oportunidade(
    session: AsyncSession, user_id: str, op_id: uuid.UUID, data: OportunidadeCriarProjeto
) -> dict:
    """Cria um PROJETO a partir da oportunidade e vincula. Reusa a RPC criar_projeto (atômica)."""
    op = await get_oportunidade(session, op_id)  # 404 se não for do dono
    if op["projeto_id"] is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "esta oportunidade já tem projeto")
    nome = data.nome or op["nome"]
    try:
        proj = (
            await session.execute(
                text(
                    """
                    select id from public.criar_projeto(
                        cast(:id as uuid), :nome, cast(:brief as jsonb))
                    """
                ),
                {"id": str(data.projeto_id), "nome": nome, "brief": json.dumps({})},
            )
        ).first()
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    if proj is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "não foi possível criar o projeto")

    try:
        await session.execute(
            text(
                "update public.oportunidades set projeto_id = cast(:p as uuid) "
                "where id = cast(:id as uuid)"
            ),
            {"p": str(data.projeto_id), "id": str(op_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or _map_conflito_projeto(e) or e) from e

    await log_event(
        session,
        tenant=user_id,
        actor_id=user_id,
        obra_id=None,
        action="oportunidade.projeto_vinculado",
        entity_type="oportunidade",
        entity_id=op_id,
        changed={"projeto_id": str(data.projeto_id)},
        entity_label=op["nome"],
        entity_seq=op["seq_humano"],
        actor_label=await actor_name(session),
    )
    return await proj_svc.get_projeto(session, data.projeto_id)


async def vincular_projeto(
    session: AsyncSession, user_id: str, op_id: uuid.UUID, data: OportunidadeVincularProjeto
) -> dict:
    """Vincula (ou desvincula, projeto_id=null) um projeto EXISTENTE do mesmo tenant."""
    op = await get_oportunidade(session, op_id)  # 404 se não for do dono
    if data.projeto_id is not None:
        # RLS já escopa projetos ao tenant: se o SELECT não vê, é de outro tenant (ou não existe).
        own = (
            await session.execute(
                text("select 1 from public.projetos where id = cast(:p as uuid)"),
                {"p": str(data.projeto_id)},
            )
        ).first()
        if own is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "projeto não encontrado no seu acervo"
            )
        # 1 projeto ↔ 1 oportunidade: erro limpo antes de bater no índice uq_oportunidades_projeto.
        ja = (
            await session.execute(
                text(
                    "select 1 from public.oportunidades "
                    "where projeto_id = cast(:p as uuid) and id <> cast(:id as uuid)"
                ),
                {"p": str(data.projeto_id), "id": str(op_id)},
            )
        ).first()
        if ja is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "este projeto já está vinculado a outra oportunidade"
            )
    try:
        await session.execute(
            text(
                "update public.oportunidades set projeto_id = :p where id = cast(:id as uuid)"
            ),
            {"p": str(data.projeto_id) if data.projeto_id else None, "id": str(op_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or _map_conflito_projeto(e) or e) from e

    acao = (
        "oportunidade.projeto_vinculado"
        if data.projeto_id
        else "oportunidade.projeto_desvinculado"
    )
    await log_event(
        session,
        tenant=user_id,
        actor_id=user_id,
        obra_id=None,
        action=acao,
        entity_type="oportunidade",
        entity_id=op_id,
        changed={"projeto_id": str(data.projeto_id) if data.projeto_id else None},
        entity_label=op["nome"],
        entity_seq=op["seq_humano"],
        actor_label=await actor_name(session),
    )
    return await get_oportunidade(session, op_id)


# ============================ comentários (timeline da negociação) ============================
_COMENT_COLS = (
    "select c.id, c.texto, p.nome as autor_nome, c.created_at, c.updated_at "
    "from public.oportunidade_comentarios c "
    "left join public.profiles p on p.id = c.created_by"
)


async def list_comentarios(session: AsyncSession, op_id: uuid.UUID) -> list[dict]:
    await get_oportunidade(session, op_id)  # 404 se não for do dono
    rows = (
        await session.execute(
            text(
                f"{_COMENT_COLS} where c.oportunidade_id = cast(:op as uuid) "
                "order by c.created_at"
            ),
            {"op": str(op_id)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def add_comentario(
    session: AsyncSession, user_id: str, op_id: uuid.UUID, data: ComentarioCreate
) -> dict:
    op = await get_oportunidade(session, op_id)  # 404 se não for do dono
    try:
        async with session.begin_nested():  # savepoint: dup id (retry) reverte sem abortar a txn
            await session.execute(
                text(
                    """
                    insert into public.oportunidade_comentarios
                      (id, oportunidade_id, tenant_id, texto, created_by)
                    values (cast(:id as uuid), cast(:op as uuid), cast(:t as uuid), :texto,
                            cast(:t as uuid))
                    """
                ),
                {"id": str(data.id), "op": str(op_id), "t": user_id, "texto": data.texto},
            )
    except IntegrityError:
        pass  # idempotente: mesmo id reenviado (offline/retry) — devolve o que já existe abaixo
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e

    await log_event(
        session,
        tenant=user_id,
        actor_id=user_id,
        obra_id=None,
        action="oportunidade.comentario_add",
        entity_type="oportunidade",
        entity_id=op_id,
        entity_label=op["nome"],
        entity_seq=op["seq_humano"],
        actor_label=await actor_name(session),
    )
    row = (
        await session.execute(
            text(f"{_COMENT_COLS} where c.id = cast(:id as uuid)"), {"id": str(data.id)}
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "não foi possível salvar o comentário")
    return dict(row._mapping)


async def edit_comentario(
    session: AsyncSession, user_id: str, op_id: uuid.UUID, c_id: uuid.UUID, data: ComentarioUpdate
) -> dict:
    op = await get_oportunidade(session, op_id)  # 404 se não for do dono
    try:
        res = (
            await session.execute(
                text(
                    "update public.oportunidade_comentarios set texto = :texto "
                    "where id = cast(:id as uuid) and oportunidade_id = cast(:op as uuid) "
                    "returning id"
                ),
                {"texto": data.texto, "id": str(c_id), "op": str(op_id)},
            )
        ).first()
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "comentário não encontrado")
    await log_event(
        session,
        tenant=user_id,
        actor_id=user_id,
        obra_id=None,
        action="oportunidade.comentario_edit",
        entity_type="oportunidade",
        entity_id=op_id,
        entity_label=op["nome"],
        entity_seq=op["seq_humano"],
        actor_label=await actor_name(session),
    )
    row = (
        await session.execute(
            text(f"{_COMENT_COLS} where c.id = cast(:id as uuid)"), {"id": str(c_id)}
        )
    ).first()
    return dict(row._mapping)


async def delete_comentario(
    session: AsyncSession, user_id: str, op_id: uuid.UUID, c_id: uuid.UUID
) -> dict:
    op = await get_oportunidade(session, op_id)  # 404 se não for do dono
    res = (
        await session.execute(
            text(
                "delete from public.oportunidade_comentarios "
                "where id = cast(:id as uuid) and oportunidade_id = cast(:op as uuid) returning id"
            ),
            {"id": str(c_id), "op": str(op_id)},
        )
    ).first()
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "comentário não encontrado")
    await log_event(
        session,
        tenant=user_id,
        actor_id=user_id,
        obra_id=None,
        action="oportunidade.comentario_del",
        entity_type="oportunidade",
        entity_id=op_id,
        entity_label=op["nome"],
        entity_seq=op["seq_humano"],
        actor_label=await actor_name(session),
    )
    return {"deleted": True}
