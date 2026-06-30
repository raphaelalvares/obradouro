"""Manual do proprietário (itens por CÔMODO, etapa `manual`). Ver migration 0101.

Espelha `services/ambientes_projeto.py`, mas SEM ciclo de aprovação (o manual é informacional: o
arquiteto cura, o cliente só LÊ). O item é uma ficha estruturada (marca/modelo/cor/fornecedor/
garantia/observações) pendurada num cômodo (`projeto_ambientes`, 0100) ou no balde "Geral"
(`ambiente_id` nulo).
O material (nota fiscal/PDF de garantia/foto/link) mora em `projeto_etapa_anexos` (0099) com
`manual_item_id` — reusa o pipeline de mídia de pipeline.py.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.pipeline import ManualItemCreate, ManualItemUpdate
from app.services.audit import log_event
from app.services.common import actor_name, projeto_writable
from app.services.storage import get_storage

# item do manual + nome do cômodo (left join — Geral fica com ambiente_nome nulo)
_MANUAL_SELECT = """
    select mi.id, mi.ambiente_id, pa.nome as ambiente_nome, mi.categoria, mi.titulo, mi.marca,
           mi.modelo, mi.cor, mi.fornecedor, mi.garantia, mi.observacoes, mi.ordem
    from public.projeto_manual_itens mi
    left join public.projeto_ambientes pa on pa.id = mi.ambiente_id
"""

# anexos do manual (com manual_item_id p/ agrupar por item); mesma forma do EtapaAnexoOut
_ANEXO_MANUAL_SELECT = """
    select id, etapa, tipo, label, url, nome_arquivo, content_type, tamanho_bytes, is_pdf,
           (thumb_key is not null) as tem_thumb, ordem, created_at, manual_item_id
    from public.projeto_etapa_anexos
"""

def _map_42501(e: DBAPIError) -> HTTPException | None:
    """Guard/RLS '42501' (ex.: arquiteto perdeu acesso no meio do request) → 403, não 500."""
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


def _map_guard(e: DBAPIError) -> HTTPException:
    """Erros do guard → HTTP: 23514 (cômodo de outro projeto) = 422; 42501 = 403."""
    sqlstate = getattr(getattr(e, "orig", None), "sqlstate", None)
    if sqlstate == "23514":
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "cômodo inválido para este projeto"
        )
    return _map_42501(e) or HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "erro ao salvar")


def _anexo_dict(r) -> dict:
    d = dict(r._mapping)
    d["etapa"] = str(d["etapa"])  # enum → str
    return d


async def _valida_ambiente(
    session: AsyncSession, projeto_id: uuid.UUID, ambiente_id: uuid.UUID | None
) -> None:
    """Se o item aponta p/ um cômodo, ele tem de existir neste projeto (404 caso contrário). O guard
    também valida (defesa em profundidade); aqui é p/ devolver 404 limpo em vez de 422 genérico."""
    if ambiente_id is None:
        return
    room = (
        await session.execute(
            text(
                "select 1 from public.projeto_ambientes "
                "where id = cast(:a as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"a": str(ambiente_id), "p": str(projeto_id)},
        )
    ).first()
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cômodo não encontrado")


async def _um(session: AsyncSession, projeto_id: uuid.UUID, item_id: uuid.UUID) -> dict:
    """Um item + seus anexos (shape ManualItemOut). 404 se não existe/não visível."""
    item = (
        await session.execute(
            text(
                f"{_MANUAL_SELECT} where mi.id = cast(:i as uuid) "
                "and mi.projeto_id = cast(:p as uuid)"
            ),
            {"i": str(item_id), "p": str(projeto_id)},
        )
    ).first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item do manual não encontrado")
    d = dict(item._mapping)
    anx = (
        await session.execute(
            text(
                f"{_ANEXO_MANUAL_SELECT} where projeto_id = cast(:p as uuid) "
                "and manual_item_id = cast(:i as uuid) order by ordem, created_at"
            ),
            {"p": str(projeto_id), "i": str(item_id)},
        )
    ).all()
    d["anexos"] = [_anexo_dict(r) for r in anx]
    return d


async def listar_manual(session: AsyncSession, projeto_id: uuid.UUID) -> list[dict]:
    """Itens do manual + anexos agrupados por item. Caller já autorizou (pipeline.listar)."""
    itens = (
        await session.execute(
            text(
                f"{_MANUAL_SELECT} where mi.projeto_id = cast(:p as uuid) "
                "order by mi.ambiente_id, mi.ordem, mi.created_at"
            ),
            {"p": str(projeto_id)},
        )
    ).all()
    anx_rows = (
        await session.execute(
            text(
                f"{_ANEXO_MANUAL_SELECT} where projeto_id = cast(:p as uuid) "
                "and etapa = 'manual' and manual_item_id is not null order by ordem, created_at"
            ),
            {"p": str(projeto_id)},
        )
    ).all()
    by_item: dict = {}
    for r in anx_rows:
        d = _anexo_dict(r)
        by_item.setdefault(str(d["manual_item_id"]), []).append(d)
    out = []
    for r in itens:
        d = dict(r._mapping)
        d["anexos"] = by_item.get(str(d["id"]), [])
        out.append(d)
    return out


async def criar(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, data: ManualItemCreate
) -> dict:
    cur = await projeto_writable(session, projeto_id)  # só arquiteto
    existing = (
        await session.execute(
            text(
                "select id from public.projeto_manual_itens "
                "where id = cast(:id as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"id": str(data.id), "p": str(projeto_id)},
        )
    ).first()
    if existing is not None:  # idempotente por id (re-POST do mesmo uuid)
        return await _um(session, projeto_id, data.id)
    await _valida_ambiente(session, projeto_id, data.ambiente_id)
    params = {
        "id": str(data.id),
        "p": str(projeto_id),
        "t": str(cur.tenant_id),
        "amb": str(data.ambiente_id) if data.ambiente_id else None,
        "categoria": data.categoria,
        "titulo": data.titulo,
        "marca": data.marca,
        "modelo": data.modelo,
        "cor": data.cor,
        "fornecedor": data.fornecedor,
        "garantia": data.garantia,
        "observacoes": data.observacoes,
        "uid": str(user_id),
    }
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    insert into public.projeto_manual_itens
                      (id, projeto_id, tenant_id, ambiente_id, categoria, titulo, marca, modelo,
                       cor, fornecedor, garantia, observacoes, ordem, created_by)
                    values (cast(:id as uuid), cast(:p as uuid), cast(:t as uuid),
                            cast(:amb as uuid), :categoria, :titulo, :marca, :modelo, :cor,
                            :fornecedor, :garantia, :observacoes,
                            (select coalesce(max(ordem), -1) + 1 from public.projeto_manual_itens
                             where projeto_id = cast(:p as uuid)
                             and ambiente_id is not distinct from cast(:amb as uuid)),
                            cast(:uid as uuid))
                    """
                ),
                params,
            )
    except IntegrityError:  # corrida do mesmo uuid (PK) → idempotente (savepoint isola)
        return await _um(session, projeto_id, data.id)
    except DBAPIError as e:
        raise _map_guard(e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="manual.item_criado",
        entity_type="projeto_manual_item",
        entity_id=data.id,
        entity_label=data.titulo,
        actor_label=await actor_name(session),
    )
    return await _um(session, projeto_id, data.id)


async def atualizar(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ManualItemUpdate,
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    prev = (
        await session.execute(
            text(
                "select id from public.projeto_manual_itens "
                "where id = cast(:i as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"i": str(item_id), "p": str(projeto_id)},
        )
    ).first()
    if prev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item do manual não encontrado")
    await _valida_ambiente(session, projeto_id, data.ambiente_id)
    params = {
        "i": str(item_id),
        "p": str(projeto_id),
        "amb": str(data.ambiente_id) if data.ambiente_id else None,
        "categoria": data.categoria,
        "titulo": data.titulo,
        "marca": data.marca,
        "modelo": data.modelo,
        "cor": data.cor,
        "fornecedor": data.fornecedor,
        "garantia": data.garantia,
        "observacoes": data.observacoes,
    }
    try:
        await session.execute(
            text(
                "update public.projeto_manual_itens set ambiente_id = cast(:amb as uuid), "
                "categoria = :categoria, titulo = :titulo, marca = :marca, modelo = :modelo, "
                "cor = :cor, fornecedor = :fornecedor, garantia = :garantia, "
                "observacoes = :observacoes "
                "where id = cast(:i as uuid) and projeto_id = cast(:p as uuid)"
            ),
            params,
        )
    except DBAPIError as e:
        raise _map_guard(e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="manual.item_atualizado",
        entity_type="projeto_manual_item",
        entity_id=item_id,
        changed={"titulo": data.titulo},
        entity_label=data.titulo,
        actor_label=await actor_name(session),
    )
    return await _um(session, projeto_id, item_id)


async def excluir(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, item_id: uuid.UUID
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    prev = (
        await session.execute(
            text(
                "select titulo from public.projeto_manual_itens "
                "where id = cast(:i as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"i": str(item_id), "p": str(projeto_id)},
        )
    ).first()
    if prev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item do manual não encontrado")
    # apaga o material (linhas + bytes) ANTES da linha; DELETE ... RETURNING fecha a janela de
    # corrida com upload concorrente. A FK cascade (manual_item_id) é só rede de segurança.
    try:
        anx = (
            await session.execute(
                text(
                    "delete from public.projeto_etapa_anexos "
                    "where projeto_id = cast(:p as uuid) and manual_item_id = cast(:i as uuid) "
                    "returning id, storage_key"
                ),
                {"p": str(projeto_id), "i": str(item_id)},
            )
        ).all()
        await session.execute(
            text("delete from public.projeto_manual_itens where id = cast(:i as uuid)"),
            {"i": str(item_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    storage = get_storage()
    for r in anx:
        if r.storage_key:
            await storage.deletar_prefixo(
                f"{cur.tenant_id}/projetos/{projeto_id}/etapas/manual/{r.id}"
            )
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="manual.item_removido",
        entity_type="projeto_manual_item",
        entity_id=item_id,
        entity_label=prev.titulo,
        actor_label=await actor_name(session),
    )
    return {"deleted": True}


async def reordenar(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, ids: list[uuid.UUID]
) -> list[dict]:
    await projeto_writable(session, projeto_id)  # só arquiteto (sem audit — proporcionalidade)
    try:
        for idx, iid in enumerate(ids):
            await session.execute(
                text(
                    "update public.projeto_manual_itens set ordem = :ord "
                    "where id = cast(:i as uuid) and projeto_id = cast(:p as uuid)"
                ),
                {"ord": idx, "i": str(iid), "p": str(projeto_id)},
            )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    return await listar_manual(session, projeto_id)
