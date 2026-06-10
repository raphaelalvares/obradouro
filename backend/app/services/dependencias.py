"""Dependências de tarefas (FS) + recálculo automático de cronograma (Fatia B).

Arestas entre tarefas TOP-LEVEL da mesma obra. O recálculo é um forward pass topológico (dias
corridos): a sucessora começa no dia seguinte ao fim do predecessor + folga. Só toca tarefas que
estão NA REDE (aparecem em alguma aresta); tarefas soltas mantêm as datas manuais. A função
`planejar` é PURA (testável sem banco). Autorização: arquiteto-only (obra_writable + guard 0061).
"""

import uuid
from datetime import date, timedelta

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.checklist import DepCreate, DepUpdate, ItemDuracaoIn
from app.services import checklist as checklist_svc
from app.services.audit import log_event
from app.services.common import actor_name, obra_writable

_DEP_SELECT = (
    "select id, predecessora_id, sucessora_id, tipo, lag_dias from public.tarefa_dependencias"
)


def _dur(t: dict) -> int:
    """Duração (dias corridos, ≥1): duracao_dias se setada; senão o span atual; senão 1 dia."""
    d = t.get("duracao_dias")
    if d:
        return max(1, int(d))
    di, df = t.get("data_inicio"), t.get("data_fim")
    if di and df:
        return max(1, (df - di).days + 1)
    return 1


def planejar(tarefas: dict, arestas: list, ancora: date) -> dict:
    """Forward pass FS (dias corridos). Retorna {id: (inicio, fim)} só p/ tarefas NA REDE (que
    aparecem em alguma aresta). Cabeça de cadeia usa o próprio data_inicio (ou a âncora); as demais
    começam no dia seguinte ao maior fim dos predecessores + folga. Levanta ValueError se houver
    ciclo (não deve ocorrer — o guard impede)."""
    na_rede: set = set()
    for a in arestas:
        na_rede.add(a["predecessora_id"])
        na_rede.add(a["sucessora_id"])
    preds: dict = {n: [] for n in na_rede}  # sucessora -> [(predecessora, lag)]
    succ: dict = {n: [] for n in na_rede}  # predecessora -> [sucessora]
    indeg: dict = dict.fromkeys(na_rede, 0)
    for a in arestas:
        s, p = a["sucessora_id"], a["predecessora_id"]
        lag = a.get("lag_dias") or 0
        preds[s].append((p, lag))
        succ[p].append(s)
        indeg[s] += 1
    fila = [n for n in na_rede if indeg[n] == 0]
    ordem: list = []
    while fila:
        n = fila.pop()
        ordem.append(n)
        for s in succ[n]:
            indeg[s] -= 1
            if indeg[s] == 0:
                fila.append(s)
    if len(ordem) != len(na_rede):
        raise ValueError("ciclo de dependências")
    res: dict = {}
    for n in ordem:
        dur = _dur(tarefas.get(n, {}))
        if preds[n]:
            inicio = max(res[p][1] + timedelta(days=1 + lag) for p, lag in preds[n])
        else:
            inicio = tarefas.get(n, {}).get("data_inicio") or ancora
        res[n] = (inicio, inicio + timedelta(days=dur - 1))
    return res


async def add_dep(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, data: DepCreate
) -> dict:
    cur = await obra_writable(session, obra_id)  # camada 1: só arquiteto
    # serializa as escritas de aresta da MESMA obra (transaction-scoped) — sem isso, dois inserts
    # concorrentes de A→B e B→A não enxergam a aresta não-commitada um do outro e fecham um ciclo
    # (o anti-ciclo só vê o snapshot da própria txn). Molde: importar_checklist (0044).
    await session.execute(
        text("select pg_advisory_xact_lock(hashtext('cria:tarefa_dep'), hashtext(:o))"),
        {"o": str(obra_id)},
    )
    # idempotente por id (re-POST do mesmo uuid devolve a aresta existente, sem re-auditar)
    existing = (
        await session.execute(
            text(f"{_DEP_SELECT} where id = cast(:id as uuid) and obra_id = cast(:o as uuid)"),
            {"id": str(data.id), "o": str(obra_id)},
        )
    ).first()
    if existing is not None:
        return dict(existing._mapping)
    if data.predecessora_id == data.sucessora_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "uma tarefa não depende de si mesma"
        )
    # pré-checa ciclo p/ devolver mensagem limpa (o guard 0061 é o backstop)
    ciclo = (
        await session.execute(
            text(
                """
                with recursive reach as (
                  select sucessora_id as n from public.tarefa_dependencias
                    where obra_id = cast(:o as uuid) and predecessora_id = cast(:s as uuid)
                  union
                  select d.sucessora_id from public.tarefa_dependencias d
                    join reach r on d.predecessora_id = r.n where d.obra_id = cast(:o as uuid)
                )
                select 1 from reach where n = cast(:p as uuid) limit 1
                """
            ),
            {"o": str(obra_id), "s": str(data.sucessora_id), "p": str(data.predecessora_id)},
        )
    ).first()
    if ciclo is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "essa dependência criaria um ciclo")
    try:
        async with session.begin_nested():  # savepoint: erro não polui a txn p/ o SELECT seguinte
            await session.execute(
                text(
                    """
                    insert into public.tarefa_dependencias
                      (id, obra_id, tenant_id, predecessora_id, sucessora_id, tipo, lag_dias,
                       created_by)
                    values (cast(:id as uuid), cast(:o as uuid), cast(:t as uuid),
                            cast(:p as uuid), cast(:s as uuid), :tipo, :lag, cast(:uid as uuid))
                    """
                ),
                {
                    "id": str(data.id),
                    "o": str(obra_id),
                    "t": str(cur.tenant_id),
                    "p": str(data.predecessora_id),
                    "s": str(data.sucessora_id),
                    "tipo": data.tipo,
                    "lag": data.lag_dias,
                    "uid": str(user_id),
                },
            )
    except IntegrityError as e:
        # unique (aresta já existe) ou check (auto-loop) → 409 limpo
        raise HTTPException(status.HTTP_409_CONFLICT, "essa dependência já existe") from e
    except DBAPIError as e:
        raise (checklist_svc._map_42501(e) or e) from e
    row = (
        await session.execute(
            text(f"{_DEP_SELECT} where id = cast(:id as uuid)"), {"id": str(data.id)}
        )
    ).first()
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="dependencia.criada",
        entity_type="tarefa_dependencia",
        entity_id=data.id,
        changed={
            "predecessora": str(data.predecessora_id),
            "sucessora": str(data.sucessora_id),
            "tipo": data.tipo,
            "lag_dias": data.lag_dias,
        },
        entity_label="dependência",
        actor_label=await actor_name(session),
    )
    return dict(row._mapping)


async def update_dep(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, dep_id: uuid.UUID, data: DepUpdate
) -> dict:
    await obra_writable(session, obra_id)  # camada 1: só arquiteto
    # ignora null explícito: tipo/lag_dias são NOT NULL no banco → tratar None como "não mexer"
    # (sem isso, {"lag_dias": null} tentaria gravar NULL e vazaria 500 em vez de no-op).
    campos = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not campos:
        # nada a mudar — devolve a aresta atual (404 se não existir)
        row = (
            await session.execute(
                text(f"{_DEP_SELECT} where id = cast(:id as uuid) and obra_id = cast(:o as uuid)"),
                {"id": str(dep_id), "o": str(obra_id)},
            )
        ).first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "dependência não encontrada")
        return dict(row._mapping)
    sets, params = [], {"id": str(dep_id), "o": str(obra_id)}
    if "tipo" in campos:
        sets.append("tipo = :tipo")
        params["tipo"] = campos["tipo"]
    if "lag_dias" in campos:
        sets.append("lag_dias = :lag")
        params["lag"] = campos["lag_dias"]
    try:
        res = await session.execute(
            text(
                f"update public.tarefa_dependencias set {', '.join(sets)} "
                "where id = cast(:id as uuid) and obra_id = cast(:o as uuid)"
            ),
            params,
        )
    except DBAPIError as e:
        raise (checklist_svc._map_42501(e) or e) from e
    if (res.rowcount or 0) == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dependência não encontrada")
    row = (
        await session.execute(
            text(f"{_DEP_SELECT} where id = cast(:id as uuid)"), {"id": str(dep_id)}
        )
    ).first()
    return dict(row._mapping)


async def delete_dep(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, dep_id: uuid.UUID
) -> dict:
    cur = await obra_writable(session, obra_id)  # camada 1: só arquiteto
    try:
        res = await session.execute(
            text(
                "delete from public.tarefa_dependencias "
                "where id = cast(:id as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"id": str(dep_id), "o": str(obra_id)},
        )
    except DBAPIError as e:
        raise (checklist_svc._map_42501(e) or e) from e
    if (res.rowcount or 0) == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dependência não encontrada")
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="dependencia.removida",
        entity_type="tarefa_dependencia",
        entity_id=dep_id,
        entity_label="dependência",
        actor_label=await actor_name(session),
    )
    return {"deleted": True}


async def set_item_duracao(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, item_id: uuid.UUID, data: ItemDuracaoIn
) -> dict:
    """Define a duração desejada da tarefa (dias corridos). Só arquiteto."""
    cur = await obra_writable(session, obra_id)
    prev = (
        await session.execute(
            text(
                "select nome, seq_humano, parent_item_id from public.checklist_itens "
                "where id = cast(:i as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"i": str(item_id), "o": str(obra_id)},
        )
    ).first()
    if prev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item não encontrado")
    # duração só faz sentido na tarefa top-level (o recálculo só lê parent_item_id is null)
    if prev.parent_item_id is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "duração só se aplica a tarefas top-level"
        )
    try:
        await session.execute(
            text(
                "update public.checklist_itens set duracao_dias = :d where id = cast(:i as uuid)"
            ),
            {"d": data.duracao_dias, "i": str(item_id)},
        )
    except DBAPIError as e:
        raise (checklist_svc._map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="item.duracao",
        entity_type="checklist_item",
        entity_id=item_id,
        changed={"duracao_dias": data.duracao_dias},
        entity_label=prev.nome,
        entity_seq=prev.seq_humano,
        actor_label=await actor_name(session),
    )
    return await checklist_svc._get_item(session, item_id)


async def recalcular(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, ancora_in: date | None
) -> dict:
    """Recalcula as datas das tarefas que estão na rede de dependências (forward pass FS). Devolve a
    árvore atualizada. Tarefas sem aresta não se mexem. Só arquiteto."""
    cur = await obra_writable(session, obra_id)
    arestas = (
        await session.execute(
            text(
                "select predecessora_id, sucessora_id, lag_dias from public.tarefa_dependencias "
                "where obra_id = cast(:o as uuid)"
            ),
            {"o": str(obra_id)},
        )
    ).all()
    arestas = [dict(a._mapping) for a in arestas]
    if not arestas:
        return await checklist_svc.get_tree(session, obra_id)  # nada encadeado → nada a fazer
    tops = (
        await session.execute(
            text(
                "select id, data_inicio, data_fim, duracao_dias from public.checklist_itens "
                "where obra_id = cast(:o as uuid) and parent_item_id is null"
            ),
            {"o": str(obra_id)},
        )
    ).all()
    tarefas = {
        r.id: {"data_inicio": r.data_inicio, "data_fim": r.data_fim, "duracao_dias": r.duracao_dias}
        for r in tops
    }
    ancora = ancora_in
    if ancora is None:
        obra = (
            await session.execute(
                text("select data_inicio from public.obras where id = cast(:o as uuid)"),
                {"o": str(obra_id)},
            )
        ).first()
        ancora = obra.data_inicio if obra else None
    if ancora is None:
        na_rede = {a["predecessora_id"] for a in arestas} | {a["sucessora_id"] for a in arestas}
        inicios = [
            tarefas[n]["data_inicio"]
            for n in na_rede
            if tarefas.get(n) and tarefas[n]["data_inicio"]
        ]
        ancora = min(inicios) if inicios else None
    if ancora is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "defina uma data de início (na obra ou no recálculo) para encadear as datas",
        )
    try:
        plano = planejar(tarefas, arestas, ancora)
    except ValueError as e:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "há um ciclo de dependências — desfaça antes de recalcular"
        ) from e
    n = 0
    try:
        for tid, (ini, fim) in plano.items():
            res = await session.execute(
                text(
                    "update public.checklist_itens set data_inicio = :di, data_fim = :df "
                    "where id = cast(:id as uuid) and obra_id = cast(:o as uuid)"
                ),
                {"di": ini, "df": fim, "id": str(tid), "o": str(obra_id)},
            )
            n += res.rowcount or 0
    except DBAPIError as e:
        raise (checklist_svc._map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="cronograma.recalculado",
        entity_type="obra",
        entity_id=obra_id,
        changed={"tarefas": n},
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return await checklist_svc.get_tree(session, obra_id)
