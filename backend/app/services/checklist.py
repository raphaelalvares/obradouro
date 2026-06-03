"""Serviço de checklist (etapas e itens).

Camadas de autorização: a RLS escopa por obra (2ª camada) e os guards no banco aplicam a regra fina
(arquiteto-only / prestador-só-estado) como backstop; aqui (camada 1) validamos cedo com
obra_writable (só arquiteto) ou obra_member (qualquer membro ativo) para devolver 403/404 limpos.

Idempotência offline: create de etapa/item é "garanta que existe" — re-POST do MESMO uuid devolve a
linha existente sem re-auditar; colisão de nome (uuid diferente, mesmo nome_norm) faz MERGE (devolve
a linha que já existe — o cliente deve re-apontar seu objeto local). Nenhum caminho usa ON CONFLICT
nas tabelas com trigger de seq (isso queimaria seq); usamos checagem de existência + INSERT em
savepoint, então só uma inserção REAL consome seq.
"""

import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.checklist import EtapaCreate, ItemCreate, ItemDetalhes, ItemEstado
from app.services import checklist_import
from app.services.audit import log_event
from app.services.common import actor_name, obra_member, obra_writable

_ETAPA_SELECT = "select id, nome, ordem, seq_humano, updated_at from public.etapas"
_ITEM_SELECT = """
    select i.id, i.etapa_id, i.nome, i.estado, i.concluido_por,
           p.nome as concluido_por_nome, i.concluido_em, i.ordem, i.seq_humano, i.updated_at,
           i.ambiente, i.unidade, i.quantidade, i.custo_mao_obra, i.custo_material, i.custo_total
    from public.checklist_itens i
    left join public.profiles p on p.id = i.concluido_por
"""


def _map_42501(e: DBAPIError) -> HTTPException | None:
    """Guard do banco (camada 2) levanta 42501 → 403 limpo (não vazar como 500)."""
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta alteração")
    return None


async def _get_etapa(session: AsyncSession, etapa_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(f"{_ETAPA_SELECT} where id = cast(:e as uuid)"), {"e": str(etapa_id)}
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "etapa não encontrada")
    return dict(row._mapping)


async def _get_item(session: AsyncSession, item_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(f"{_ITEM_SELECT} where i.id = cast(:i as uuid)"), {"i": str(item_id)}
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item não encontrado")
    return dict(row._mapping)


# ============================ leitura (árvore) ============================
async def get_tree(session: AsyncSession, obra_id: uuid.UUID) -> dict:
    await obra_member(session, obra_id)  # 404 se não-membro (RLS devolveria vazio; 404 é honesto)
    etapas = (
        await session.execute(
            text(f"{_ETAPA_SELECT} where obra_id = cast(:o as uuid) order by ordem, seq_humano"),
            {"o": str(obra_id)},
        )
    ).all()
    itens = (
        await session.execute(
            text(
                f"{_ITEM_SELECT} where i.obra_id = cast(:o as uuid) order by i.ordem, i.seq_humano"
            ),
            {"o": str(obra_id)},
        )
    ).all()
    by_etapa: dict = {}
    for it in itens:
        by_etapa.setdefault(it.etapa_id, []).append(dict(it._mapping))
    return {
        "obra_id": obra_id,
        "etapas": [{**dict(e._mapping), "itens": by_etapa.get(e.id, [])} for e in etapas],
    }


# ============================ etapas ============================
async def create_etapa(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, data: EtapaCreate
) -> dict:
    cur = await obra_writable(session, obra_id)  # camada 1: só arquiteto
    # re-POST do MESMO uuid → idempotente (sem INSERT, sem queimar seq, sem re-auditar)
    existing = (
        await session.execute(
            text(f"{_ETAPA_SELECT} where id = cast(:e as uuid)"), {"e": str(data.id)}
        )
    ).first()
    if existing is not None:
        return dict(existing._mapping)

    norm = checklist_import.norm_nome(data.nome)
    try:
        async with session.begin_nested():  # savepoint: erro reverte INSERT+seq sem poluir a txn
            row = (
                await session.execute(
                    text(
                        """
                        insert into public.etapas (id, obra_id, tenant_id, nome, nome_norm, ordem)
                        values (cast(:id as uuid), cast(:o as uuid), cast(:t as uuid),
                                :n, :nn, :ord)
                        returning id, nome, ordem, seq_humano, updated_at
                        """
                    ),
                    {
                        "id": str(data.id),
                        "o": str(obra_id),
                        "t": str(cur.tenant_id),
                        "n": data.nome,
                        "nn": norm,
                        "ord": data.ordem,
                    },
                )
            ).first()
    except IntegrityError:
        return await _merge_existing_etapa(session, obra_id, data.id, norm)
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e

    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="etapa.criada",
        entity_type="etapa",
        entity_id=data.id,
        entity_label=row.nome,
        entity_seq=row.seq_humano,
        actor_label=await actor_name(session),
    )
    return dict(row._mapping)


async def _merge_existing_etapa(
    session: AsyncSession, obra_id: uuid.UUID, etapa_id: uuid.UUID, norm: str
) -> dict:
    """Colisão: concorrente com o MESMO uuid, ou outra etapa com o MESMO nome (merge)."""
    by_id = (
        await session.execute(
            text(f"{_ETAPA_SELECT} where id = cast(:e as uuid)"), {"e": str(etapa_id)}
        )
    ).first()
    if by_id is not None:
        return dict(by_id._mapping)
    by_name = (
        await session.execute(
            text(f"{_ETAPA_SELECT} where obra_id = cast(:o as uuid) and nome_norm = :nn"),
            {"o": str(obra_id), "nn": norm},
        )
    ).first()
    if by_name is not None:
        return dict(by_name._mapping)
    raise HTTPException(status.HTTP_409_CONFLICT, "conflito ao criar etapa")


async def rename_etapa(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, etapa_id: uuid.UUID, novo_nome: str
) -> dict:
    cur = await obra_writable(session, obra_id)
    prev = (
        await session.execute(
            text(
                "select nome, seq_humano from public.etapas "
                "where id = cast(:e as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"e": str(etapa_id), "o": str(obra_id)},
        )
    ).first()
    if prev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "etapa não encontrada")
    if novo_nome == prev.nome:
        return await _get_etapa(session, etapa_id)
    try:
        await session.execute(
            text("update public.etapas set nome = :n, nome_norm = :nn where id = cast(:e as uuid)"),
            {"n": novo_nome, "nn": checklist_import.norm_nome(novo_nome), "e": str(etapa_id)},
        )
    except IntegrityError as e:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "já existe etapa com esse nome nesta obra"
        ) from e
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="etapa.renomeada",
        entity_type="etapa",
        entity_id=etapa_id,
        changed={"nome": {"de": prev.nome, "para": novo_nome}},
        entity_label=novo_nome,
        entity_seq=prev.seq_humano,
        actor_label=await actor_name(session),
    )
    return await _get_etapa(session, etapa_id)


async def reorder_etapa(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, etapa_id: uuid.UUID, ordem: int
) -> dict:
    await obra_writable(session, obra_id)  # só arquiteto; reorder não audita (proporcionalidade)
    res = (
        await session.execute(
            text(
                "update public.etapas set ordem = :ord "
                "where id = cast(:e as uuid) and obra_id = cast(:o as uuid) returning id"
            ),
            {"ord": ordem, "e": str(etapa_id), "o": str(obra_id)},
        )
    ).first()
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "etapa não encontrada")
    return await _get_etapa(session, etapa_id)


async def delete_etapa(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, etapa_id: uuid.UUID
) -> dict:
    cur = await obra_writable(session, obra_id)
    prev = (
        await session.execute(
            text(
                "select nome, seq_humano from public.etapas "
                "where id = cast(:e as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"e": str(etapa_id), "o": str(obra_id)},
        )
    ).first()
    if prev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "etapa não encontrada")
    # snapshot dos filhos ANTES do cascade → 1 evento item.removido por filho (audit é CORE)
    filhos = (
        await session.execute(
            text(
                "select id, nome, seq_humano, estado from public.checklist_itens "
                "where etapa_id = cast(:e as uuid)"
            ),
            {"e": str(etapa_id)},
        )
    ).all()
    alabel = await actor_name(session)
    for f in filhos:
        await log_event(
            session,
            tenant=cur.tenant_id,
            actor_id=user_id,
            obra_id=obra_id,
            action="item.removido",
            entity_type="checklist_item",
            entity_id=f.id,
            changed={"etapa_id": str(etapa_id), "estado_final": f.estado, "via": "etapa.removida"},
            entity_label=f.nome,
            entity_seq=f.seq_humano,
            actor_label=alabel,
        )
    await session.execute(
        text("delete from public.etapas where id = cast(:e as uuid)"), {"e": str(etapa_id)}
    )
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="etapa.removida",
        entity_type="etapa",
        entity_id=etapa_id,
        changed={"itens_removidos": len(filhos)},
        entity_label=prev.nome,
        entity_seq=prev.seq_humano,
        actor_label=alabel,
    )
    return {"deleted": True, "itens_removidos": len(filhos)}


# ============================ itens ============================
async def create_item(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, data: ItemCreate
) -> dict:
    cur = await obra_writable(session, obra_id)  # só arquiteto
    existing = (
        await session.execute(
            text(f"{_ITEM_SELECT} where i.id = cast(:i as uuid)"), {"i": str(data.id)}
        )
    ).first()
    if existing is not None:
        return dict(existing._mapping)

    norm = checklist_import.norm_nome(data.nome)
    try:
        async with session.begin_nested():
            new_id = (
                await session.execute(
                    text(
                        """
                        insert into public.checklist_itens
                          (id, etapa_id, obra_id, tenant_id, nome, nome_norm, ordem,
                           ambiente, unidade, quantidade,
                           custo_mao_obra, custo_material, custo_total)
                        values (cast(:id as uuid), cast(:e as uuid), cast(:o as uuid),
                                cast(:t as uuid), :n, :nn, :ord,
                                :amb, :un, :qt, :cmo, :cmat, :ctot)
                        returning id
                        """
                    ),
                    {
                        "id": str(data.id),
                        "e": str(data.etapa_id),
                        "o": str(obra_id),
                        "t": str(cur.tenant_id),
                        "n": data.nome,
                        "nn": norm,
                        "ord": data.ordem,
                        "amb": data.ambiente,
                        "un": data.unidade,
                        "qt": data.quantidade,
                        "cmo": data.custo_mao_obra,
                        "cmat": data.custo_material,
                        "ctot": data.custo_total,
                    },
                )
            ).scalar_one()
    except IntegrityError:
        return await _merge_existing_item(session, data.etapa_id, data.id, norm)
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e

    row = await _get_item(session, new_id)
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="item.criado",
        entity_type="checklist_item",
        entity_id=data.id,
        changed={"etapa_id": str(data.etapa_id)},
        entity_label=row["nome"],
        entity_seq=row["seq_humano"],
        actor_label=await actor_name(session),
    )
    return row


async def _merge_existing_item(
    session: AsyncSession, etapa_id: uuid.UUID, item_id: uuid.UUID, norm: str
) -> dict:
    by_id = (
        await session.execute(
            text(f"{_ITEM_SELECT} where i.id = cast(:i as uuid)"), {"i": str(item_id)}
        )
    ).first()
    if by_id is not None:
        return dict(by_id._mapping)
    by_name = (
        await session.execute(
            text(f"{_ITEM_SELECT} where i.etapa_id = cast(:e as uuid) and i.nome_norm = :nn"),
            {"e": str(etapa_id), "nn": norm},
        )
    ).first()
    if by_name is not None:
        return dict(by_name._mapping)
    raise HTTPException(status.HTTP_409_CONFLICT, "conflito ao criar item")


async def rename_item(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, item_id: uuid.UUID, novo_nome: str
) -> dict:
    cur = await obra_writable(session, obra_id)  # só arquiteto
    prev = (
        await session.execute(
            text(
                "select nome, seq_humano from public.checklist_itens "
                "where id = cast(:i as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"i": str(item_id), "o": str(obra_id)},
        )
    ).first()
    if prev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item não encontrado")
    if novo_nome == prev.nome:
        return await _get_item(session, item_id)
    try:
        await session.execute(
            text(
                "update public.checklist_itens set nome = :n, nome_norm = :nn "
                "where id = cast(:i as uuid)"
            ),
            {"n": novo_nome, "nn": checklist_import.norm_nome(novo_nome), "i": str(item_id)},
        )
    except IntegrityError as e:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "já existe item com esse nome nesta etapa"
        ) from e
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="item.renomeado",
        entity_type="checklist_item",
        entity_id=item_id,
        changed={"nome": {"de": prev.nome, "para": novo_nome}},
        entity_label=novo_nome,
        entity_seq=prev.seq_humano,
        actor_label=await actor_name(session),
    )
    return await _get_item(session, item_id)


# colunas que o PATCH de detalhes pode tocar (allowlist; vão pro SQL, então NÃO vêm do usuário)
_DETALHE_COLS = (
    "ambiente", "unidade", "quantidade", "custo_mao_obra", "custo_material", "custo_total"
)


async def atualizar_detalhes(
    session: AsyncSession,
    user_id: str,
    obra_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ItemDetalhes,
) -> dict:
    """PATCH parcial de cômodo/orçamento do item (só arquiteto). Aplica apenas os campos enviados
    (exclude_unset); o guard do banco (camada 2) reforça que prestador/cliente não passam aqui."""
    cur = await obra_writable(session, obra_id)  # camada 1: só arquiteto
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if k in _DETALHE_COLS}
    prev = (
        await session.execute(
            text(
                "select seq_humano, nome from public.checklist_itens "
                "where id = cast(:i as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"i": str(item_id), "o": str(obra_id)},
        )
    ).first()
    if prev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item não encontrado")
    if not fields:
        return await _get_item(session, item_id)

    sets = ", ".join(f"{k} = :{k}" for k in fields)  # k ∈ allowlist fixa → seguro
    params = dict(fields)
    params["i"] = str(item_id)
    try:
        await session.execute(
            text(f"update public.checklist_itens set {sets} where id = cast(:i as uuid)"), params
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    row = await _get_item(session, item_id)
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="item.detalhes",
        entity_type="checklist_item",
        entity_id=item_id,
        changed=fields,
        entity_label=row["nome"],
        entity_seq=prev.seq_humano,
        actor_label=await actor_name(session),
    )
    return row


async def delete_item(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, item_id: uuid.UUID
) -> dict:
    cur = await obra_writable(session, obra_id)
    prev = (
        await session.execute(
            text(
                "select etapa_id, nome, seq_humano, estado from public.checklist_itens "
                "where id = cast(:i as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"i": str(item_id), "o": str(obra_id)},
        )
    ).first()
    if prev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item não encontrado")
    await session.execute(
        text("delete from public.checklist_itens where id = cast(:i as uuid)"), {"i": str(item_id)}
    )
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="item.removido",
        entity_type="checklist_item",
        entity_id=item_id,
        changed={"etapa_id": str(prev.etapa_id), "estado_final": prev.estado},
        entity_label=prev.nome,
        entity_seq=prev.seq_humano,
        actor_label=await actor_name(session),
    )
    return {"deleted": True}


async def set_item_estado(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, item_id: uuid.UUID, data: ItemEstado
) -> dict:
    cur = await obra_member(session, obra_id)  # membro ativo; cliente é read-only nesta fase
    if cur.papel not in ("arquiteto", "prestador"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "cliente não altera o checklist nesta fase")
    # FOR UPDATE: trava a linha p/ a txn → captura o 'de' real e evita lost-update concorrente
    locked = (
        await session.execute(
            text(
                "select estado, nome, seq_humano from public.checklist_itens "
                "where id = cast(:i as uuid) and obra_id = cast(:o as uuid) for update"
            ),
            {"i": str(item_id), "o": str(obra_id)},
        )
    ).first()
    if locked is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item não encontrado")
    # conflito offline: base do cliente não bate com o servidor (vale mesmo se o alvo já é o atual)
    if data.estado_de is not None and data.estado_de != locked.estado:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"estado mudou no servidor (agora '{locked.estado}')"
        )
    if locked.estado == data.estado:  # no-op idempotente (re-tap/retry) → sem audit
        return await _get_item(session, item_id)
    try:
        await session.execute(
            text(
                """
                update public.checklist_itens set
                  estado = cast(:novo as public.estado_item),
                  concluido_por = case when cast(:novo as public.estado_item) = 'concluido'
                                       then cast(:uid as uuid) else null end,
                  concluido_em  = case when cast(:novo as public.estado_item) = 'concluido'
                                       then now() else null end
                where id = cast(:i as uuid)
                """
            ),
            {"novo": data.estado, "uid": str(user_id), "i": str(item_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="item.estado_alterado",
        entity_type="checklist_item",
        entity_id=item_id,
        changed={"estado": {"de": locked.estado, "para": data.estado}},
        entity_label=locked.nome,
        entity_seq=locked.seq_humano,
        actor_label=await actor_name(session),
    )
    return await _get_item(session, item_id)


# ============================ import ============================
async def importar(session: AsyncSession, user_id: str, obra_id: uuid.UUID, arquivo) -> dict:
    cur = await obra_writable(session, obra_id)  # camada 1: só arquiteto
    raw = await arquivo.read()
    # auto-detecta: template do app OU planilha de orçamento real (etapas+serviços+valores).
    payload = checklist_import.parse_xlsx(raw)  # valida formato/tamanho/linhas → 413/422
    if not payload:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "planilha vazia ou fora do padrão"
        )
    for e in payload:  # UUID por nó (gerado fora do banco; reutilizado só se a linha for nova)
        e["id"] = str(uuid.uuid4())
        for it in e["itens"]:
            it["id"] = str(uuid.uuid4())
    try:
        row = (
            await session.execute(
                text(
                    """
                    select etapas_novas, etapas_existentes, itens_novos, itens_existentes
                    from public.importar_checklist(cast(:o as uuid), cast(:p as jsonb))
                    """
                ),
                {"o": str(obra_id), "p": json.dumps(payload)},
            )
        ).first()
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    resumo = dict(row._mapping)
    # evento de roll-up: a importação é uma ação SOBRE a obra (etapa.criada/item.criado por linha
    # nova já foram emitidos dentro da RPC). entity_type='obra' p/ não inventar pseudo-entidade.
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="checklist.importado",
        entity_type="obra",
        entity_id=obra_id,
        changed=resumo,
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return resumo
