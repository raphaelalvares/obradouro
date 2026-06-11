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

from app.schemas.checklist import (
    CronogramaAplicarIn,
    DatasIn,
    EtapaConclusao,
    EtapaCreate,
    ItemCreate,
    ItemDetalhes,
    ItemEstado,
)
from app.services import ambientes as ambientes_svc
from app.services import checklist_import
from app.services.audit import log_event
from app.services.common import actor_name, obra_member, obra_writable

_ETAPA_SELECT = (
    "select id, nome, ordem, seq_humano, updated_at, data_inicio, data_fim, "
    "concluida, concluida_em from public.etapas"
)
_ITEM_SELECT = """
    select i.id, i.etapa_id, i.parent_item_id, i.nome, i.estado, i.concluido_por,
           p.nome as concluido_por_nome, i.concluido_em, i.ordem, i.seq_humano, i.updated_at,
           i.data_inicio, i.data_fim, i.duracao_dias,
           i.ambiente, i.ambiente_id, i.equipe_id,
           i.unidade, i.quantidade, i.custo_mao_obra, i.custo_material, i.custo_total
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
    cur = await obra_member(session, obra_id)  # 404 se não-membro (RLS daria vazio; 404 é honesto)
    # M2 (produto): custos do checklist visíveis a ARQUITETO e CLIENTE; ocultos ao PRESTADOR.
    # Mascarado na API (visibilidade por-coluna/papel não cabe na RLS; ver C3 p/ fechar o Path B).
    mascarar_custo = cur.papel == "prestador"
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
    # 3 níveis: etapa → tarefas (top-level) → subitens (filhos). A query já vem ordenada por
    # ordem/seq, então top-level e filhos saem na ordem certa ao distribuir.
    rows = [dict(it._mapping) for it in itens]
    for r in rows:
        r["subitens"] = []
        if mascarar_custo:
            r["custo_mao_obra"] = r["custo_material"] = r["custo_total"] = None
    by_id = {r["id"]: r for r in rows}
    top_by_etapa: dict = {}
    itens_por_etapa: dict = {}  # TODOS os itens (top + sub) por etapa, p/ derivar as datas da etapa
    tops: list[dict] = []  # tarefas top-level (alvo das dependências)
    for r in rows:
        itens_por_etapa.setdefault(r["etapa_id"], []).append(r)
        pid = r["parent_item_id"]
        if pid is not None and pid in by_id:
            by_id[pid]["subitens"].append(r)
        else:
            top_by_etapa.setdefault(r["etapa_id"], []).append(r)
            tops.append(r)
    deps = (
        await session.execute(
            text(
                "select id, predecessora_id, sucessora_id, tipo, lag_dias "
                "from public.tarefa_dependencias where obra_id = cast(:o as uuid)"
            ),
            {"o": str(obra_id)},
        )
    ).all()
    deps = [dict(d._mapping) for d in deps]
    _marcar_bloqueio(tops, deps)
    ambientes = (
        await session.execute(
            text(
                "select id, nome, ordem, area_m2 from public.ambientes "
                "where obra_id = cast(:o as uuid) order by ordem, created_at"
            ),
            {"o": str(obra_id)},
        )
    ).all()
    return {
        "obra_id": obra_id,
        "etapas": [_etapa_tree(e, top_by_etapa, itens_por_etapa) for e in etapas],
        "dependencias": deps,
        "ambientes": [dict(a._mapping) for a in ambientes],
    }


def _tarefa_concluida(top: dict) -> bool:
    """Tarefa top-level 'concluída': se tem sub-itens, todos concluídos; senão, ela própria."""
    if top["subitens"]:
        return all(s["estado"] == "concluido" for s in top["subitens"])
    return top["estado"] == "concluido"


def _marcar_bloqueio(tops: list[dict], deps: list[dict]) -> None:
    """Anota bloqueada/aguarda em cada tarefa top-level: bloqueada = tem predecessor não-concluído;
    aguarda = seq_humano dos predecessores que faltam. Mutaciona os dicts in-place."""
    feito = {t["id"]: _tarefa_concluida(t) for t in tops}
    seq = {t["id"]: t["seq_humano"] for t in tops}
    preds: dict = {}
    for d in deps:
        preds.setdefault(d["sucessora_id"], []).append(d["predecessora_id"])
    for t in tops:
        faltam = [p for p in preds.get(t["id"], []) if not feito.get(p, True)]
        t["bloqueada"] = bool(faltam)
        t["aguarda"] = [seq[p] for p in faltam if seq.get(p) is not None]


async def _predecessores_pendentes(
    session: AsyncSession, obra_id: uuid.UUID, top_id: uuid.UUID
) -> list[int]:
    """seq_humano dos predecessores (tarefa-top) de `top_id` que NÃO estão 100% concluídos.
    'Concluído' = tarefa-folha com estado='concluido' OU tarefa com todos os sub-itens feitos."""
    rows = (
        await session.execute(
            text(
                """
                select p.seq_humano
                from public.tarefa_dependencias d
                join public.checklist_itens p on p.id = d.predecessora_id
                where d.sucessora_id = cast(:t as uuid) and d.obra_id = cast(:o as uuid)
                  and not (
                    case when exists (select 1 from public.checklist_itens c
                                      where c.parent_item_id = p.id)
                      then not exists (select 1 from public.checklist_itens c
                                       where c.parent_item_id = p.id and c.estado <> 'concluido')
                      else p.estado = 'concluido'
                    end
                  )
                order by p.seq_humano
                """
            ),
            {"t": str(top_id), "o": str(obra_id)},
        )
    ).all()
    return [r.seq_humano for r in rows if r.seq_humano is not None]


def _etapa_tree(etapa, top_by_etapa: dict, itens_por_etapa: dict) -> dict:
    """Monta a etapa com itens + datas EFETIVAS: min/max das datas dos itens; se a etapa não tem
    itens, usa as datas próprias (e marca sem_itens p/ o front liberar a edição direta)."""
    its = itens_por_etapa.get(etapa.id, [])
    if its:
        inis = [r["data_inicio"] for r in its if r["data_inicio"] is not None]
        fims = [r["data_fim"] for r in its if r["data_fim"] is not None]
        data_inicio = min(inis) if inis else None
        data_fim = max(fims) if fims else None
        sem_itens = False
    else:
        data_inicio, data_fim, sem_itens = etapa.data_inicio, etapa.data_fim, True
    return {
        **dict(etapa._mapping),
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "sem_itens": sem_itens,
        "itens": top_by_etapa.get(etapa.id, []),
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
    # cômodo no create (a API aceita ambiente texto): resolve-or-create → grava ambiente_id + nome
    # canônico, mantendo o invariante "tem texto ⇒ tem id" (igual atualizar_detalhes).
    amb_id: uuid.UUID | None = None
    amb_nome: str | None = data.ambiente
    if data.ambiente and data.ambiente.strip():
        amb_id, amb_nome = await ambientes_svc.resolver(
            session, obra_id, cur.tenant_id, data.ambiente
        )
    else:
        amb_nome = None
    try:
        async with session.begin_nested():
            new_id = (
                await session.execute(
                    text(
                        """
                        insert into public.checklist_itens
                          (id, etapa_id, parent_item_id, obra_id, tenant_id, nome, nome_norm, ordem,
                           ambiente, ambiente_id, unidade, quantidade,
                           custo_mao_obra, custo_material, custo_total)
                        values (cast(:id as uuid), cast(:e as uuid),
                                cast(:pid as uuid), cast(:o as uuid),
                                cast(:t as uuid), :n, :nn, :ord,
                                :amb, cast(:amb_id as uuid), :un, :qt, :cmo, :cmat, :ctot)
                        returning id
                        """
                    ),
                    {
                        "id": str(data.id),
                        "e": str(data.etapa_id),
                        "pid": str(data.parent_item_id) if data.parent_item_id else None,
                        "o": str(obra_id),
                        "t": str(cur.tenant_id),
                        "n": data.nome,
                        "nn": norm,
                        "ord": data.ordem,
                        "amb": amb_nome,
                        "amb_id": str(amb_id) if amb_id else None,
                        "un": data.unidade,
                        "qt": data.quantidade,
                        "cmo": data.custo_mao_obra,
                        "cmat": data.custo_material,
                        "ctot": data.custo_total,
                    },
                )
            ).scalar_one()
    except IntegrityError:
        return await _merge_existing_item(
            session, data.etapa_id, data.id, norm, data.parent_item_id
        )
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
    session: AsyncSession,
    etapa_id: uuid.UUID,
    item_id: uuid.UUID,
    norm: str,
    parent_item_id: uuid.UUID | None = None,
) -> dict:
    by_id = (
        await session.execute(
            text(f"{_ITEM_SELECT} where i.id = cast(:i as uuid)"), {"i": str(item_id)}
        )
    ).first()
    if by_id is not None:
        return dict(by_id._mapping)
    # dedupe no MESMO nível: sub-item por (pai, nome_norm); tarefa top-level por (etapa, nome_norm).
    if parent_item_id is not None:
        by_name = (
            await session.execute(
                text(
                    f"{_ITEM_SELECT} where i.parent_item_id = cast(:p as uuid) "
                    "and i.nome_norm = :nn"
                ),
                {"p": str(parent_item_id), "nn": norm},
            )
        ).first()
    else:
        by_name = (
            await session.execute(
                text(
                    f"{_ITEM_SELECT} where i.etapa_id = cast(:e as uuid) "
                    "and i.parent_item_id is null and i.nome_norm = :nn"
                ),
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
    dump = data.model_dump(exclude_unset=True)
    fields = {k: v for k, v in dump.items() if k in _DETALHE_COLS}
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
    # equipe é nível-tenant (≠ ambiente/orçamento): tratada à parte (cast uuid). Presente no payload
    # (mesmo None) = "setar"; valida que a equipe é do tenant (RLS self) p/ um 404 limpo (o guard do
    # banco backstopa cross-tenant). Não está em _DETALHE_COLS p/ não ir cru ao SQL.
    set_equipe = "equipe_id" in dump
    equipe_id = dump.get("equipe_id")
    if set_equipe and equipe_id is not None:
        # ancora no DONO DA OBRA (cur.tenant_id), NÃO em auth.uid(): mesma âncora do guard do banco
        # (eq.tenant_id = new.tenant_id), então as duas camadas concordam (a equipe tem de ser do
        # dono da obra). No caso comum (arquiteto = dono da conta) coincidem; alinhar evita 403
        # espúrio se um dia houver co-arquiteto.
        existe = (
            await session.execute(
                text(
                    "select 1 from public.equipes "
                    "where id = cast(:e as uuid) and tenant_id = cast(:t as uuid)"
                ),
                {"e": str(equipe_id), "t": str(cur.tenant_id)},
            )
        ).first()
        if existe is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "equipe não encontrada")
    if not fields and not set_equipe:
        return await _get_item(session, item_id)

    # cômodo: o texto vira registro (resolve-or-create) → grava também ambiente_id + nome canônico.
    amb_id: uuid.UUID | None = None
    set_ambiente_id = False
    if "ambiente" in fields:
        set_ambiente_id = True
        nome_amb = (fields["ambiente"] or "").strip()
        if nome_amb:
            amb_id, canonical = await ambientes_svc.resolver(
                session, obra_id, cur.tenant_id, nome_amb
            )
            fields["ambiente"] = canonical
        else:
            fields["ambiente"] = None

    sets = [f"{k} = :{k}" for k in fields]  # k ∈ allowlist fixa → seguro
    params = dict(fields)
    if set_ambiente_id:
        sets.append("ambiente_id = cast(:ambiente_id as uuid)")
        params["ambiente_id"] = str(amb_id) if amb_id else None
    if set_equipe:
        sets.append("equipe_id = cast(:equipe_id as uuid)")
        params["equipe_id"] = str(equipe_id) if equipe_id else None
        fields["equipe_id"] = params["equipe_id"]  # entra no audit (changed)
    params["i"] = str(item_id)
    sql_sets = ", ".join(sets)
    try:
        await session.execute(
            text(f"update public.checklist_itens set {sql_sets} where id = cast(:i as uuid)"),
            params,
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
                "select estado, nome, seq_humano, parent_item_id from public.checklist_itens "
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
    # poka-yoke de dependência: não dá p/ INICIAR/CONCLUIR uma tarefa (ou seu sub-item) enquanto
    # algum predecessor da tarefa-top não estiver concluído. Voltar p/ 'pendente' nunca bloqueia.
    if data.estado in ("em_andamento", "concluido"):
        top_id = locked.parent_item_id or item_id
        faltam = await _predecessores_pendentes(session, obra_id, top_id)
        if faltam:
            quem = ", ".join(f"#{s}" for s in faltam)
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"tarefa bloqueada por dependência (aguarda {quem})",
            )
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


# ============================ cronograma (datas) ============================
async def set_item_datas(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, item_id: uuid.UUID, data: DatasIn
) -> dict:
    """Define início/fim de UMA tarefa (item). Só arquiteto."""
    cur = await obra_writable(session, obra_id)
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
    try:
        await session.execute(
            text(
                "update public.checklist_itens set data_inicio = :di, data_fim = :df "
                "where id = cast(:i as uuid)"
            ),
            {"di": data.data_inicio, "df": data.data_fim, "i": str(item_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    row = await _get_item(session, item_id)
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="item.cronograma",
        entity_type="checklist_item",
        entity_id=item_id,
        changed={"data_inicio": str(data.data_inicio), "data_fim": str(data.data_fim)},
        entity_label=row["nome"],
        entity_seq=prev.seq_humano,
        actor_label=await actor_name(session),
    )
    return row


async def set_etapa_datas(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, etapa_id: uuid.UUID, data: DatasIn
) -> dict:
    """Define início/fim direto na ETAPA (só vale quando a etapa não tem itens). Só arquiteto."""
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
    try:
        await session.execute(
            text(
                "update public.etapas set data_inicio = :di, data_fim = :df "
                "where id = cast(:e as uuid)"
            ),
            {"di": data.data_inicio, "df": data.data_fim, "e": str(etapa_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="etapa.cronograma",
        entity_type="etapa",
        entity_id=etapa_id,
        changed={"data_inicio": str(data.data_inicio), "data_fim": str(data.data_fim)},
        entity_label=prev.nome,
        entity_seq=prev.seq_humano,
        actor_label=await actor_name(session),
    )
    return await _get_etapa(session, etapa_id)


async def set_etapa_concluida(
    session: AsyncSession,
    user_id: str,
    obra_id: uuid.UUID,
    etapa_id: uuid.UUID,
    data: EtapaConclusao,
) -> dict:
    """Marca/desmarca a ETAPA como concluída (marco). Pensado p/ etapas sem tarefas, que não têm
    checklist p/ derivar a conclusão; alimenta o status do Gantt. Só arquiteto."""
    cur = await obra_writable(session, obra_id)
    # FOR UPDATE: trava a linha → base real do 'de' e evita lost-update concorrente.
    locked = (
        await session.execute(
            text(
                "select concluida, nome, seq_humano from public.etapas "
                "where id = cast(:e as uuid) and obra_id = cast(:o as uuid) for update"
            ),
            {"e": str(etapa_id), "o": str(obra_id)},
        )
    ).first()
    if locked is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "etapa não encontrada")
    # conflito offline: base do cliente não bate com o servidor.
    if data.concluida_de is not None and data.concluida_de != locked.concluida:
        raise HTTPException(status.HTTP_409_CONFLICT, "a conclusão mudou no servidor")
    if locked.concluida == data.concluida:  # no-op idempotente (re-tap) → sem audit
        return await _get_etapa(session, etapa_id)
    try:
        await session.execute(
            text(
                """
                update public.etapas set
                  concluida = cast(:c as boolean),
                  concluida_em = case when cast(:c as boolean) then now() else null end,
                  concluida_por = case
                    when cast(:c as boolean) then cast(:uid as uuid) else null end
                where id = cast(:e as uuid)
                """
            ),
            {"c": data.concluida, "uid": str(user_id), "e": str(etapa_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="etapa.conclusao_alterada",
        entity_type="etapa",
        entity_id=etapa_id,
        changed={"concluida": {"de": locked.concluida, "para": data.concluida}},
        entity_label=locked.nome,
        entity_seq=locked.seq_humano,
        actor_label=await actor_name(session),
    )
    return await _get_etapa(session, etapa_id)


async def aplicar_cronograma(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, data: CronogramaAplicarIn
) -> dict:
    """Aplica o 'cronograma macro' (prévia editada): datas dos itens/etapas + janela da obra, tudo
    numa transação. Só arquiteto. Devolve a árvore atualizada (datas da etapa derivam dos itens)."""
    cur = await obra_writable(session, obra_id)
    n_itens = n_etapas = 0
    try:
        for ent in data.entradas:
            if ent.tipo == "item":
                res = await session.execute(
                    text(
                        "update public.checklist_itens set data_inicio = :di, data_fim = :df "
                        "where id = cast(:id as uuid) and obra_id = cast(:o as uuid)"
                    ),
                    {
                        "di": ent.data_inicio,
                        "df": ent.data_fim,
                        "id": str(ent.id),
                        "o": str(obra_id),
                    },
                )
            else:
                res = await session.execute(
                    text(
                        "update public.etapas set data_inicio = :di, data_fim = :df "
                        "where id = cast(:id as uuid) and obra_id = cast(:o as uuid)"
                    ),
                    {
                        "di": ent.data_inicio,
                        "df": ent.data_fim,
                        "id": str(ent.id),
                        "o": str(obra_id),
                    },
                )
            afetadas = res.rowcount or 0
            if ent.tipo == "item":
                n_itens += afetadas
            else:
                n_etapas += afetadas
        if data.obra_data_inicio is not None or data.obra_data_fim is not None:
            await session.execute(
                text(
                    "update public.obras set data_inicio = :di, data_fim = :df "
                    "where id = cast(:o as uuid)"
                ),
                {"di": data.obra_data_inicio, "df": data.obra_data_fim, "o": str(obra_id)},
            )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="cronograma.aplicado",
        entity_type="obra",
        entity_id=obra_id,
        changed={
            "itens": n_itens,
            "etapas": n_etapas,
            "obra_inicio": str(data.obra_data_inicio),
            "obra_fim": str(data.obra_data_fim),
        },
        entity_label=cur.nome,
        entity_seq=cur.seq_humano,
        actor_label=await actor_name(session),
    )
    return await get_tree(session, obra_id)


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
    # o RPC grava o ambiente como TEXTO; liga ao registro (cria cômodos novos + seta ambiente_id).
    await ambientes_svc.reconciliar(session, obra_id, cur.tenant_id)
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
