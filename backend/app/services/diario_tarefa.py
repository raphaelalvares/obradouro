"""Avanço por TAREFA lançado no diário (medição SNAPSHOT, datada pela data do diário).

Cada linha liga uma entrada do diário a UMA folha do checklist com o progresso (0..100) na data.
É a fonte do progresso real da obra: após gravar/editar, o item recebe a denormalização via a função
`recalcular_progresso_item` (0083) — FONTE ÚNICA da sincronização progresso↔estado, compartilhada
com o gatilho de recálculo no DELETE (inclui CASCADE de diário/tarefa). Quem executa a obra escreve
(o guard 0082 refina: prestador só no diário próprio); cliente lê. Fotos da tarefa via anexos
(parent_type='diario_tarefa')."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.acompanhamento import DiarioTarefaIn
from app.services.audit import log_event
from app.services.common import actor_name, obra_executor, obra_member

_SELECT = """
    select dt.id, dt.item_id, i.nome as item_nome, i.seq_humano as item_seq, e.nome as etapa_nome,
           dt.progresso_pct, dt.qtd_executada, i.unidade, i.quantidade, dt.observacao,
           dt.created_by,
           (select count(*) from public.anexos a
            where a.parent_type = 'diario_tarefa' and a.parent_id = dt.id) as n_fotos,
           dt.created_at, dt.updated_at
    from public.diario_tarefas dt
    join public.checklist_itens i on i.id = dt.item_id
    join public.etapas e on e.id = i.etapa_id
"""


def _f(v) -> float | None:
    return float(v) if v is not None else None


def derivar_pct(
    qtd_executada: float | None, quantidade: float | None, pct_informado: float | None
) -> float:
    """PURA (testável). % do avanço: se a tarefa tem `quantidade`(>0) e veio `qtd_executada`, deriva
    do executado; senão usa o % informado. Clamp 0..100, 2 casas. Degenerado (só qtd, sem total) → 0
    (o front só oferece entrada por qtd quando a tarefa tem quantidade)."""
    if qtd_executada is not None and quantidade is not None and quantidade > 0:
        pct = (qtd_executada / quantidade) * 100
    elif pct_informado is not None:
        pct = pct_informado
    else:
        pct = 0.0
    return max(0.0, min(100.0, round(float(pct), 2)))


def _map_42501(e: DBAPIError) -> HTTPException | None:
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta alteração")
    return None


async def _get(session: AsyncSession, obra_id: uuid.UUID, dt_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(f"{_SELECT} where dt.id = cast(:i as uuid) and dt.obra_id = cast(:o as uuid)"),
            {"i": str(dt_id), "o": str(obra_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "medição não encontrada")
    return dict(row._mapping)


async def listar_do_diario(
    session: AsyncSession, obra_id: uuid.UUID, diario_id: uuid.UUID
) -> list[dict]:
    await obra_member(session, obra_id)  # qualquer membro ativo vê
    rows = (
        await session.execute(
            text(
                f"{_SELECT} where dt.obra_id = cast(:o as uuid) "
                "and dt.diario_id = cast(:d as uuid) order by dt.created_at"
            ),
            {"o": str(obra_id), "d": str(diario_id)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def _recalcular(session: AsyncSession, item_id: uuid.UUID) -> None:
    """Sincroniza progresso_pct/estado do item pela função do banco (fonte única, 0083)."""
    await session.execute(
        text("select public.recalcular_progresso_item(cast(:i as uuid))"), {"i": str(item_id)}
    )


async def definir(
    session: AsyncSession,
    user_id: str,
    obra_id: uuid.UUID,
    diario_id: uuid.UUID,
    data: DiarioTarefaIn,
) -> dict:
    """Upsert por (diario, tarefa): cria ou atualiza a medição daquela tarefa naquele diário."""
    cur = await obra_executor(session, obra_id)  # guard 0082 refina prestador-só-diário-próprio
    # diário existe na obra? (404 limpo antes do guard 23514)
    if (
        await session.execute(
            text(
                "select 1 from public.diario_obra "
                "where id = cast(:d as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"d": str(diario_id), "o": str(obra_id)},
        )
    ).first() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "registro de diário não encontrado")
    # item da obra (pega quantidade p/ derivar % por qtd; o guard reforça folha/obra)
    item = (
        await session.execute(
            text(
                "select i.quantidade, exists (select 1 from public.checklist_itens c "
                "where c.parent_item_id = i.id) as tem_filhos "
                "from public.checklist_itens i "
                "where i.id = cast(:i as uuid) and i.obra_id = cast(:o as uuid)"
            ),
            {"i": str(data.item_id), "o": str(obra_id)},
        )
    ).first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "tarefa não encontrada nesta obra")
    # avanço só na FOLHA (espelha set_item_estado): agregador deriva dos filhos. Pré-checa p/ 422
    # limpo — senão o guard 0082 levanta 23514 e cai no ramo do UNIQUE (IntegrityError crua → 500).
    if item.tem_filhos:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "só é possível medir o avanço de uma tarefa-folha (sem subtarefas)",
        )
    pct = derivar_pct(data.qtd_executada, _f(item.quantidade), data.progresso_pct)

    existing = (
        await session.execute(
            text(
                "select id from public.diario_tarefas "
                "where diario_id = cast(:d as uuid) and item_id = cast(:i as uuid)"
            ),
            {"d": str(diario_id), "i": str(data.item_id)},
        )
    ).first()
    upd = text(
        "update public.diario_tarefas "
        "set progresso_pct = :p, qtd_executada = :q, observacao = :obs "
        "where id = cast(:id as uuid)"
    )
    novo = existing is None
    try:
        if existing is not None:
            await session.execute(
                upd, {"p": pct, "q": data.qtd_executada, "obs": data.observacao,
                      "id": str(existing.id)},
            )
            dt_id = existing.id
        else:
            async with session.begin_nested():
                await session.execute(
                    text(
                        """
                        insert into public.diario_tarefas
                          (id, diario_id, item_id, obra_id, tenant_id, progresso_pct, qtd_executada,
                           observacao, created_by)
                        values (cast(:id as uuid), cast(:d as uuid), cast(:i as uuid),
                                cast(:o as uuid), cast(:t as uuid), :p, :q, :obs,
                                (select auth.uid()))
                        """
                    ),
                    {
                        "id": str(data.id), "d": str(diario_id), "i": str(data.item_id),
                        "o": str(obra_id), "t": str(cur.tenant_id), "p": pct,
                        "q": data.qtd_executada, "obs": data.observacao,
                    },
                )
            dt_id = data.id
    except IntegrityError:
        # corrida no UNIQUE (diario,item): outra txn inseriu a medição → vira UPDATE da existente.
        race = (
            await session.execute(
                text(
                    "select id from public.diario_tarefas "
                    "where diario_id = cast(:d as uuid) and item_id = cast(:i as uuid)"
                ),
                {"d": str(diario_id), "i": str(data.item_id)},
            )
        ).first()
        if race is None:
            raise
        await session.execute(
            upd, {"p": pct, "q": data.qtd_executada, "obs": data.observacao, "id": str(race.id)}
        )
        dt_id, novo = race.id, False
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e

    await _recalcular(session, data.item_id)
    row = await _get(session, obra_id, dt_id)
    await log_event(
        session, tenant=cur.tenant_id, actor_id=user_id, obra_id=obra_id,
        action="diario_tarefa.definida", entity_type="diario_tarefa", entity_id=dt_id,
        changed={"diario_id": str(diario_id), "item_id": str(data.item_id),
                 "progresso_pct": pct, "novo": novo},
        entity_label=row["item_nome"], entity_seq=row["item_seq"],
        actor_label=await actor_name(session),
    )
    return row


async def excluir(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, dt_id: uuid.UUID
) -> dict:
    """Remove a medição. O gatilho AFTER DELETE (0083) recalcula o progresso do item; as fotos da
    medição são limpas pelo gatilho de órfãos (0084)."""
    cur = await obra_executor(session, obra_id)  # guard 0082 refina prestador-só-diário-próprio
    prev = await _get(session, obra_id, dt_id)
    try:
        await session.execute(
            text(
                "delete from public.diario_tarefas "
                "where id = cast(:i as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"i": str(dt_id), "o": str(obra_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session, tenant=cur.tenant_id, actor_id=user_id, obra_id=obra_id,
        action="diario_tarefa.removida", entity_type="diario_tarefa", entity_id=dt_id,
        changed={"item_id": str(prev["item_id"])}, entity_label=prev["item_nome"],
        entity_seq=prev["item_seq"], actor_label=await actor_name(session),
    )
    return {"deleted": True}
