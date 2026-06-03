"""Estoque por NF-e (Fase 6): import idempotente do XML, conferência (qtd nota × contada),
edição do nome fiel ao XML, data de chegada (≠ emissão) e saldo por material. Camadas:
service (papel) + RLS + guards. Import via RPC SECURITY DEFINER `importar_nfe` (idempotente pela
chave). Bytes do XML guardados como texto na própria linha (sem storage)."""

import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.audit import log_event
from app.services.common import actor_name, obra_executor, obra_member, obra_writable
from app.services.nfe_parser import NFeParseError, parse_nfe

settings = get_settings()


def _map_42501(e: DBAPIError) -> HTTPException | None:
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


_ITEM_SELECT = """
    select i.id, i.codigo, i.descricao, i.nome_editado,
           coalesce(i.nome_editado, i.descricao) as nome,
           i.ncm, i.unidade, i.quantidade_nota, i.valor_unitario, i.valor_total,
           i.quantidade_conferida, i.conferido_por, p.nome as conferido_por_nome, i.conferido_em,
           (i.quantidade_conferida is not null
            and i.quantidade_conferida <> i.quantidade_nota) as divergente,
           i.ordem, i.created_at
    from public.nota_itens i
    left join public.profiles p on p.id = i.conferido_por
"""


# ============================ import ============================
async def importar(session: AsyncSession, user_id: str, obra_id: uuid.UUID, arquivo) -> dict:
    await obra_writable(session, obra_id)  # camada 1: só arquiteto
    raw = await arquivo.read()
    if not raw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "arquivo vazio")
    if len(raw) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"arquivo acima do limite de {settings.MAX_UPLOAD_MB} MB",
        )
    try:
        nfe = parse_nfe(raw)
    except NFeParseError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e

    payload = {
        "id": str(uuid.uuid4()),
        "chave": nfe["chave"],
        "numero": nfe["numero"],
        "serie": nfe["serie"],
        "emitente_nome": nfe["emitente_nome"],
        "emitente_cnpj": nfe["emitente_cnpj"],
        "data_emissao": nfe["data_emissao"],
        "valor_total": nfe["valor_total"],
        "xml": raw.decode("utf-8", errors="replace"),
        "itens": [{**it, "id": str(uuid.uuid4())} for it in nfe["itens"]],
    }
    try:
        row = (
            await session.execute(
                text(
                    """
                    select nota_id, criada, itens_novos
                    from public.importar_nfe(cast(:o as uuid), cast(:p as jsonb))
                    """
                ),
                {"o": str(obra_id), "p": json.dumps(payload)},
            )
        ).first()
    except DBAPIError as e:
        msg = str(getattr(e, "orig", e))
        if "chave de acesso invalida" in msg:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "chave de acesso inválida"
            ) from e
        raise (_map_42501(e) or e) from e
    return dict(row._mapping)


# ============================ leitura ============================
_NOTA_COLS = """
    n.id, n.seq_humano, n.numero, n.serie, n.chave_acesso, n.emitente_nome, n.emitente_cnpj,
    n.data_emissao, n.data_chegada, n.valor_total, n.created_at
"""


async def list_notas(session: AsyncSession, obra_id: uuid.UUID) -> list[dict]:
    await obra_member(session, obra_id)
    rows = (
        await session.execute(
            text(
                f"""
                select {_NOTA_COLS},
                       count(i.id) as total_itens,
                       count(i.quantidade_conferida) as itens_conferidos,
                       count(i.id) filter (
                         where i.quantidade_conferida is not null
                           and i.quantidade_conferida <> i.quantidade_nota
                       ) as itens_divergentes
                from public.notas_fiscais n
                left join public.nota_itens i on i.nota_id = n.id
                where n.obra_id = cast(:o as uuid)
                group by n.id
                order by n.created_at desc
                """
            ),
            {"o": str(obra_id)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def get_nota(session: AsyncSession, obra_id: uuid.UUID, nota_id: uuid.UUID) -> dict:
    await obra_member(session, obra_id)
    nota = (
        await session.execute(
            text(
                f"""
                select {_NOTA_COLS},
                       count(i.id) as total_itens,
                       count(i.quantidade_conferida) as itens_conferidos,
                       count(i.id) filter (
                         where i.quantidade_conferida is not null
                           and i.quantidade_conferida <> i.quantidade_nota
                       ) as itens_divergentes
                from public.notas_fiscais n
                left join public.nota_itens i on i.nota_id = n.id
                where n.id = cast(:n as uuid) and n.obra_id = cast(:o as uuid)
                group by n.id
                """
            ),
            {"n": str(nota_id), "o": str(obra_id)},
        )
    ).first()
    if nota is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "nota não encontrada")
    itens = (
        await session.execute(
            text(
                f"{_ITEM_SELECT} "
                "where i.nota_id = cast(:n as uuid) order by i.ordem, i.created_at"
            ),
            {"n": str(nota_id)},
        )
    ).all()
    out = dict(nota._mapping)
    out["itens"] = [dict(r._mapping) for r in itens]
    return out


async def saldo(session: AsyncSession, obra_id: uuid.UUID) -> list[dict]:
    await obra_member(session, obra_id)
    rows = (
        await session.execute(
            text(
                """
                select coalesce(nullif(i.nome_editado, ''), i.descricao) as nome,
                       i.unidade,
                       sum(coalesce(i.quantidade_conferida, i.quantidade_nota)) as quantidade_total,
                       sum(coalesce(i.valor_total, 0)) as valor_total
                from public.nota_itens i
                where i.obra_id = cast(:o as uuid)
                group by 1, 2
                order by 1
                """
            ),
            {"o": str(obra_id)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


# ============================ edição da nota / item ============================
async def _item_or_404(session: AsyncSession, obra_id: uuid.UUID, item_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(f"{_ITEM_SELECT} where i.id = cast(:i as uuid) and i.obra_id = cast(:o as uuid)"),
            {"i": str(item_id), "o": str(obra_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item não encontrado")
    return dict(row._mapping)


async def atualizar_nota(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, nota_id: uuid.UUID, data
) -> dict:
    cur = await obra_writable(session, obra_id)
    try:
        res = (
            await session.execute(
                text(
                    """update public.notas_fiscais set data_chegada = cast(:d as date)
                       where id = cast(:n as uuid) and obra_id = cast(:o as uuid)
                       returning seq_humano"""
                ),
                {"d": data.data_chegada, "n": str(nota_id), "o": str(obra_id)},
            )
        ).first()
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "nota não encontrada")
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="nota.data_chegada",
        entity_type="nota_fiscal",
        entity_id=nota_id,
        changed={"data_chegada": str(data.data_chegada) if data.data_chegada else None},
        entity_label=f"Nota #{res.seq_humano}",
        entity_seq=res.seq_humano,
        actor_label=await actor_name(session),
    )
    return await get_nota(session, obra_id, nota_id)


async def excluir_nota(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, nota_id: uuid.UUID
) -> dict:
    cur = await obra_writable(session, obra_id)
    try:
        res = (
            await session.execute(
                text(
                    """delete from public.notas_fiscais
                       where id = cast(:n as uuid) and obra_id = cast(:o as uuid)
                       returning seq_humano, numero"""
                ),
                {"n": str(nota_id), "o": str(obra_id)},
            )
        ).first()
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "nota não encontrada")
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="nota.removida",
        entity_type="nota_fiscal",
        entity_id=nota_id,
        entity_label=f"Nota #{res.seq_humano}",
        entity_seq=res.seq_humano,
        actor_label=await actor_name(session),
    )
    return {"deleted": True}


async def editar_nome_item(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, item_id: uuid.UUID, data
) -> dict:
    cur = await obra_writable(session, obra_id)  # só arquiteto corrige o nome
    nome = (data.nome_editado or "").strip() or None
    try:
        res = (
            await session.execute(
                text(
                    """update public.nota_itens set nome_editado = :nome
                       where id = cast(:i as uuid) and obra_id = cast(:o as uuid)
                       returning descricao"""
                ),
                {"nome": nome, "i": str(item_id), "o": str(obra_id)},
            )
        ).first()
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item não encontrado")
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="nota.item_renomeado",
        entity_type="nota_item",
        entity_id=item_id,
        changed={"nome_editado": nome, "descricao_xml": res.descricao},
        entity_label=nome or res.descricao,
        actor_label=await actor_name(session),
    )
    return await _item_or_404(session, obra_id, item_id)


async def conferir_item(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, item_id: uuid.UUID, data
) -> dict:
    cur = await obra_executor(session, obra_id)  # arquiteto OU prestador confere
    q = data.quantidade_conferida
    try:
        res = (
            await session.execute(
                text(
                    """
                    update public.nota_itens set
                      quantidade_conferida = cast(:q as numeric),
                      conferido_por = case when :q2 is null then null else (select auth.uid()) end,
                      conferido_em  = case when :q2 is null then null else now() end
                    where id = cast(:i as uuid) and obra_id = cast(:o as uuid)
                    returning descricao, nome_editado, quantidade_nota
                    """
                ),
                {"q": q, "q2": q, "i": str(item_id), "o": str(obra_id)},
            )
        ).first()
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item não encontrado")
    divergente = q is not None and float(q) != float(res.quantidade_nota)
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="nota.item_conferido",
        entity_type="nota_item",
        entity_id=item_id,
        changed={
            "quantidade_conferida": q,
            "quantidade_nota": float(res.quantidade_nota),
            "divergente": divergente,
        },
        entity_label=res.nome_editado or res.descricao,
        actor_label=await actor_name(session),
    )
    return await _item_or_404(session, obra_id, item_id)
