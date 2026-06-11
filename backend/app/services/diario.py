"""Diário de obra (Fatia C). Relato datado da execução. Quem EXECUTA a obra (arquiteto OU prestador)
registra; cliente lê. Editar/apagar: arquiteto qualquer, prestador só a própria (reforçado no guard
0066 → 42501 → 403). Fotos via anexos (parent_type='diario').

Efetivo (0067): quebra por FUNÇÃO/cargo [{funcao_id, nome(snapshot), qtd}] em
diario_obra.efetivo_itens (jsonb); o TOTAL fica em diario_obra.efetivo, mantido aqui = soma das
qtds. Funções = biblioteca do DONO da obra (validadas em funcoes.mapa_da_obra; guard reforça)."""

import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.acompanhamento import DiarioCreate, DiarioUpdate
from app.services import funcoes as funcoes_svc
from app.services.audit import log_event
from app.services.common import actor_name, obra_executor, obra_member

_SELECT = """
    select d.id, d.data, d.texto, d.clima, d.efetivo, d.efetivo_itens, d.seq_humano, d.created_by,
           d.created_at, d.updated_at, p.nome as autor_nome,
           (select count(*) from public.anexos a
            where a.parent_type = 'diario' and a.parent_id = d.id) as n_fotos
    from public.diario_obra d
    left join public.profiles p on p.id = d.created_by
"""
_PATCH_COLS = ("data", "texto", "clima")  # efetivo_itens é tratado à parte (derivado + jsonb)


def consolidar_efetivo(itens, mapa: dict[str, str]) -> tuple[str, int | None]:
    """PURA (testável). Valida cada funcao_id contra `mapa` ({id: nome} das funções da obra), soma
    duplicatas (mantém a ordem da 1ª aparição) e devolve (jsonb_str, total). Vazio → ('[]', None);
    funcao_id fora do mapa → 404. O `nome` gravado é sempre o do `mapa` (canônico, anti-tamper)."""
    if not itens:
        return "[]", None
    soma: dict[str, int] = {}
    ordem: list[str] = []
    for it in itens:
        fid = str(it.funcao_id)
        if fid not in mapa:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "função não encontrada nesta obra")
        if fid not in soma:
            ordem.append(fid)
        soma[fid] = soma.get(fid, 0) + int(it.qtd)
    arr = [{"funcao_id": fid, "nome": mapa[fid], "qtd": soma[fid]} for fid in ordem]
    return json.dumps(arr), sum(soma.values())


def _norm(mapping) -> dict:
    """Linha do _SELECT → dict; efetivo_itens sempre como list (asyncpg devolve jsonb como str)."""
    d = dict(mapping)
    ei = d.get("efetivo_itens")
    d["efetivo_itens"] = json.loads(ei) if isinstance(ei, str) else (ei or [])
    return d


def _map_42501(e: DBAPIError) -> HTTPException | None:
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta alteração")
    return None


async def _get(session: AsyncSession, obra_id: uuid.UUID, diario_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(f"{_SELECT} where d.id = cast(:i as uuid) and d.obra_id = cast(:o as uuid)"),
            {"i": str(diario_id), "o": str(obra_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "registro de diário não encontrado")
    return _norm(row._mapping)


async def listar(session: AsyncSession, obra_id: uuid.UUID) -> list[dict]:
    await obra_member(session, obra_id)  # qualquer membro ativo vê o diário
    rows = (
        await session.execute(
            text(
                f"{_SELECT} where d.obra_id = cast(:o as uuid) "
                "order by d.data desc, d.created_at desc"
            ),
            {"o": str(obra_id)},
        )
    ).all()
    return [_norm(r._mapping) for r in rows]


async def criar(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, data: DiarioCreate
) -> dict:
    cur = await obra_executor(session, obra_id)  # arquiteto OU prestador
    # idempotente por id (re-POST do mesmo uuid offline) → devolve o existente sem queimar seq.
    # check escopado por obra (id é PK GLOBAL): id de OUTRA obra cai no INSERT → 23505 abaixo.
    existing = (
        await session.execute(
            text(
                "select 1 from public.diario_obra "
                "where id = cast(:i as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"i": str(data.id), "o": str(obra_id)},
        )
    ).first()
    if existing is not None:
        return await _get(session, obra_id, data.id)
    itens_json, total = "[]", None
    if data.efetivo_itens:
        mapa = await funcoes_svc.mapa_da_obra(session, obra_id)
        itens_json, total = consolidar_efetivo(data.efetivo_itens, mapa)
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    insert into public.diario_obra
                      (id, obra_id, tenant_id, data, texto, clima, efetivo, efetivo_itens,
                       created_by)
                    values (cast(:id as uuid), cast(:o as uuid), cast(:t as uuid), :data, :texto,
                            :clima, :efetivo, cast(:itens as jsonb), (select auth.uid()))
                    """
                ),
                {
                    "id": str(data.id), "o": str(obra_id), "t": str(cur.tenant_id),
                    "data": data.data, "texto": data.texto, "clima": data.clima,
                    "efetivo": total, "itens": itens_json,
                },
            )
    except IntegrityError as e:
        # corrida no MESMO id (offline): re-POST concorrente colidiu na PK → devolve o existente da
        # obra; id de OUTRA obra (PK global) → 409 limpo (não 500).
        existe = (
            await session.execute(
                text(
                    "select 1 from public.diario_obra "
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
        session, tenant=cur.tenant_id, actor_id=user_id, obra_id=obra_id, action="diario.criado",
        entity_type="diario", entity_id=data.id, entity_label=str(data.data),
        entity_seq=row["seq_humano"], actor_label=await actor_name(session),
    )
    return row


async def atualizar(
    session: AsyncSession,
    user_id: str,
    obra_id: uuid.UUID,
    diario_id: uuid.UUID,
    data: DiarioUpdate,
) -> dict:
    cur = await obra_executor(session, obra_id)  # guard reforça "prestador só a própria"
    prev = await _get(session, obra_id, diario_id)
    dump = data.model_dump(exclude_unset=True)
    fields = {k: v for k, v in dump.items() if k in _PATCH_COLS}
    set_efetivo = "efetivo_itens" in dump
    if not fields and not set_efetivo:
        return prev
    sets = [f"{k} = :{k}" for k in fields]
    params = {**fields, "i": str(diario_id), "o": str(obra_id)}
    changed = dict(fields)
    if set_efetivo:
        itens_json, total = "[]", None
        if data.efetivo_itens:
            mapa = await funcoes_svc.mapa_da_obra(session, obra_id)
            itens_json, total = consolidar_efetivo(data.efetivo_itens, mapa)
        sets += ["efetivo = :efetivo", "efetivo_itens = cast(:itens as jsonb)"]
        params["efetivo"] = total
        params["itens"] = itens_json
        changed["efetivo"] = total
    try:
        await session.execute(
            text(
                f"update public.diario_obra set {', '.join(sets)} "
                "where id = cast(:i as uuid) and obra_id = cast(:o as uuid)"
            ),
            params,
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session, tenant=cur.tenant_id, actor_id=user_id, obra_id=obra_id, action="diario.editado",
        entity_type="diario", entity_id=diario_id, changed=changed,
        entity_label=str(fields.get("data", prev["data"])), entity_seq=prev["seq_humano"],
        actor_label=await actor_name(session),
    )
    return await _get(session, obra_id, diario_id)


async def excluir(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, diario_id: uuid.UUID
) -> dict:
    cur = await obra_executor(session, obra_id)  # guard reforça "prestador só a própria"
    prev = await _get(session, obra_id, diario_id)
    try:
        await session.execute(
            text(
                "delete from public.diario_obra "
                "where id = cast(:i as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"i": str(diario_id), "o": str(obra_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session, tenant=cur.tenant_id, actor_id=user_id, obra_id=obra_id, action="diario.removido",
        entity_type="diario", entity_id=diario_id, entity_label=str(prev["data"]),
        entity_seq=prev["seq_humano"], actor_label=await actor_name(session),
    )
    return {"deleted": True}
