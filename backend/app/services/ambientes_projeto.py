"""3D / aprovação por AMBIENTE (cômodos do projeto, etapa `projeto_3d`). Ver migration 0100.

Espelha `services/ambientes.py` (obra), mas a nível de PROJETO e SEM o denorm/backfill de
checklist_itens. Carrega o estado da aprovação 3D por cômodo (estado único que recicla:
rascunho → pendente → aprovado | alteracao_pedida). O arquiteto cria/edita/envia; o cliente decide
(`decidir_3d`); a DECISÃO é carimbada pelo servidor no guard (M9). O material 3D (renders/links)
mora em `projeto_etapa_anexos` (0099) com `ambiente_id` — reusa o pipeline de mídia de pipeline.py.
"""

import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.pipeline import AmbienteProjetoCreate, AmbienteProjetoUpdate, Aprovacao3DDecisao
from app.services.audit import log_event
from app.services.common import actor_name, projeto_member, projeto_writable
from app.services.storage import get_storage

# cômodo + estado da aprovação 3D (decidido_por_nome p/ exibição legível)
_SELECT_3D = """
    select pa.id, pa.nome, pa.ordem, pa.status_3d, pa.motivo_3d, pa.decidido_por_3d,
           p.nome as decidido_por_nome, pa.decidido_em_3d as decidido_em
    from public.projeto_ambientes pa
    left join public.profiles p on p.id = pa.decidido_por_3d
"""

# anexos 3D (com ambiente_id p/ agrupar por cômodo); mesma forma do EtapaAnexoOut
_ANEXO_3D_SELECT = """
    select id, etapa, tipo, label, url, nome_arquivo, content_type, tamanho_bytes, is_pdf,
           (thumb_key is not null) as tem_thumb, ordem, created_at, ambiente_id
    from public.projeto_etapa_anexos
"""


def _limpo(nome: str) -> str:
    """Colapsa whitespace ASCII + trim (classe ASCII explícita, ≠ \\s; ver ambientes.py)."""
    return re.sub(r"[ \t\n\r\f\v]+", " ", nome or "").strip()


def _map_42501(e: DBAPIError) -> HTTPException | None:
    """Guard/RLS '42501' (ex.: arquiteto perdeu acesso no meio do request) → 403, não 500."""
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


def _anexo_dict(r) -> dict:
    d = dict(r._mapping)
    d["etapa"] = str(d["etapa"])  # enum → str
    return d


async def _um(session: AsyncSession, projeto_id: uuid.UUID, amb_id: uuid.UUID) -> dict:
    """Um cômodo + seus anexos 3D (shape Ambiente3DOut). 404 se não existe/não visível."""
    room = (
        await session.execute(
            text(
                f"{_SELECT_3D} where pa.id = cast(:a as uuid) "
                "and pa.projeto_id = cast(:p as uuid)"
            ),
            {"a": str(amb_id), "p": str(projeto_id)},
        )
    ).first()
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cômodo não encontrado")
    d = dict(room._mapping)
    d["status_3d"] = str(d["status_3d"])
    anx = (
        await session.execute(
            text(
                f"{_ANEXO_3D_SELECT} where projeto_id = cast(:p as uuid) "
                "and ambiente_id = cast(:a as uuid) order by ordem, created_at"
            ),
            {"p": str(projeto_id), "a": str(amb_id)},
        )
    ).all()
    d["anexos"] = [_anexo_dict(r) for r in anx]
    return d


async def listar_3d(session: AsyncSession, projeto_id: uuid.UUID) -> list[dict]:
    """Cômodos do projeto + anexos 3D agrupados por cômodo. Caller já autorizou (pipeline)."""
    rooms = (
        await session.execute(
            text(
                f"{_SELECT_3D} where pa.projeto_id = cast(:p as uuid) "
                "order by pa.ordem, pa.created_at"
            ),
            {"p": str(projeto_id)},
        )
    ).all()
    anx_rows = (
        await session.execute(
            text(
                f"{_ANEXO_3D_SELECT} where projeto_id = cast(:p as uuid) "
                "and etapa = 'projeto_3d' and ambiente_id is not null order by ordem, created_at"
            ),
            {"p": str(projeto_id)},
        )
    ).all()
    by_amb: dict = {}
    for r in anx_rows:
        d = _anexo_dict(r)
        by_amb.setdefault(str(d["ambiente_id"]), []).append(d)
    out = []
    for r in rooms:
        d = dict(r._mapping)
        d["status_3d"] = str(d["status_3d"])
        d["anexos"] = by_amb.get(str(d["id"]), [])
        out.append(d)
    return out


async def criar(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, data: AmbienteProjetoCreate
) -> dict:
    cur = await projeto_writable(session, projeto_id)  # só arquiteto
    existing = (
        await session.execute(
            text(
                "select id from public.projeto_ambientes "
                "where id = cast(:id as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"id": str(data.id), "p": str(projeto_id)},
        )
    ).first()
    if existing is not None:  # idempotente por id (re-POST do mesmo uuid)
        return await _um(session, projeto_id, data.id)
    limpo = _limpo(data.nome)
    nn = limpo.lower()
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    insert into public.projeto_ambientes
                      (id, projeto_id, tenant_id, nome, nome_norm, ordem, created_by)
                    values (cast(:id as uuid), cast(:p as uuid), cast(:t as uuid), :nome, :nn,
                            (select coalesce(max(ordem), -1) + 1 from public.projeto_ambientes
                             where projeto_id = cast(:p as uuid)),
                            cast(:uid as uuid))
                    """
                ),
                {
                    "id": str(data.id),
                    "p": str(projeto_id),
                    "t": str(cur.tenant_id),
                    "nome": limpo,
                    "nn": nn,
                    "uid": str(user_id),
                },
            )
    except IntegrityError:  # nome já existe (outro uuid) → MERGE: devolve o existente
        row = (
            await session.execute(
                text(
                    "select id from public.projeto_ambientes "
                    "where projeto_id = cast(:p as uuid) and nome_norm = :nn"
                ),
                {"p": str(projeto_id), "nn": nn},
            )
        ).first()
        if row is None:  # corrida: o conflitante foi removido entre o INSERT e o re-select
            raise HTTPException(status.HTTP_409_CONFLICT, "conflito ao criar cômodo") from None
        return await _um(session, projeto_id, row.id)
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="ambiente_3d.criado",
        entity_type="projeto_ambiente",
        entity_id=data.id,
        entity_label=limpo,
        actor_label=await actor_name(session),
    )
    return await _um(session, projeto_id, data.id)


async def atualizar(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    amb_id: uuid.UUID,
    data: AmbienteProjetoUpdate,
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    campos = data.model_dump(exclude_unset=True)
    prev = (
        await session.execute(
            text(
                "select nome from public.projeto_ambientes "
                "where id = cast(:a as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"a": str(amb_id), "p": str(projeto_id)},
        )
    ).first()
    if prev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cômodo não encontrado")
    if "nome" not in campos or not campos["nome"]:
        return await _um(session, projeto_id, amb_id)
    novo_nome = _limpo(campos["nome"])
    try:
        await session.execute(
            text(
                "update public.projeto_ambientes set nome = :nome, nome_norm = :nn "
                "where id = cast(:a as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"nome": novo_nome, "nn": novo_nome.lower(), "a": str(amb_id), "p": str(projeto_id)},
        )
    except IntegrityError as e:  # rename colidiu com outro cômodo do projeto
        raise HTTPException(status.HTTP_409_CONFLICT, "já existe um cômodo com esse nome") from e
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="ambiente_3d.renomeado",
        entity_type="projeto_ambiente",
        entity_id=amb_id,
        changed={"nome": novo_nome},
        entity_label=novo_nome,
        actor_label=await actor_name(session),
    )
    return await _um(session, projeto_id, amb_id)


async def excluir(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, amb_id: uuid.UUID
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    prev = (
        await session.execute(
            text(
                "select nome from public.projeto_ambientes "
                "where id = cast(:a as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"a": str(amb_id), "p": str(projeto_id)},
        )
    ).first()
    if prev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cômodo não encontrado")
    # apaga o material 3D (linhas + bytes) ANTES da linha; DELETE ... RETURNING fecha a janela de
    # corrida com upload concorrente (sem SELECT-then-DELETE). A FK cascade é só rede de segurança.
    try:
        anx = (
            await session.execute(
                text(
                    "delete from public.projeto_etapa_anexos "
                    "where projeto_id = cast(:p as uuid) and ambiente_id = cast(:a as uuid) "
                    "returning id, storage_key"
                ),
                {"p": str(projeto_id), "a": str(amb_id)},
            )
        ).all()
        await session.execute(
            text("delete from public.projeto_ambientes where id = cast(:a as uuid)"),
            {"a": str(amb_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    storage = get_storage()
    for r in anx:
        if r.storage_key:
            await storage.deletar_prefixo(
                f"{cur.tenant_id}/projetos/{projeto_id}/etapas/projeto_3d/{r.id}"
            )
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="ambiente_3d.removido",
        entity_type="projeto_ambiente",
        entity_id=amb_id,
        entity_label=prev.nome,
        actor_label=await actor_name(session),
    )
    return {"deleted": True}


async def reordenar(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, ids: list[uuid.UUID]
) -> list[dict]:
    await projeto_writable(session, projeto_id)  # só arquiteto (sem audit — proporcionalidade)
    try:
        for idx, aid in enumerate(ids):
            await session.execute(
                text(
                    "update public.projeto_ambientes set ordem = :ord "
                    "where id = cast(:a as uuid) and projeto_id = cast(:p as uuid)"
                ),
                {"ord": idx, "a": str(aid), "p": str(projeto_id)},
            )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    return await listar_3d(session, projeto_id)


async def enviar_3d(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, amb_id: uuid.UUID
) -> dict:
    """Arquiteto envia o 3D do cômodo p/ aprovação (rascunho|alteracao_pedida → pendente).
    Exige ≥1 anexo. O guard zera a decisão anterior do cliente ao mudar o status."""
    cur = await projeto_writable(session, projeto_id)
    room = (
        await session.execute(
            text(
                "select status_3d, nome from public.projeto_ambientes "
                "where id = cast(:a as uuid) and projeto_id = cast(:p as uuid) for update"
            ),
            {"a": str(amb_id), "p": str(projeto_id)},
        )
    ).first()
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cômodo não encontrado")
    if str(room.status_3d) not in ("rascunho", "alteracao_pedida"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "este cômodo já está em aprovação ou aprovado"
        )
    n = (
        await session.execute(
            text(
                "select count(*) from public.projeto_etapa_anexos "
                "where projeto_id = cast(:p as uuid) and ambiente_id = cast(:a as uuid)"
            ),
            {"p": str(projeto_id), "a": str(amb_id)},
        )
    ).scalar_one()
    if not n:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "anexe ao menos um render ou link antes de enviar"
        )
    try:
        await session.execute(
            text(
                "update public.projeto_ambientes set status_3d = 'pendente' "
                "where id = cast(:a as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"a": str(amb_id), "p": str(projeto_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="ambiente_3d.enviado",
        entity_type="projeto_ambiente",
        entity_id=amb_id,
        entity_label=room.nome,
        actor_label=await actor_name(session),
    )
    return await _um(session, projeto_id, amb_id)


async def decidir_3d(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    amb_id: uuid.UUID,
    data: Aprovacao3DDecisao,
) -> dict:
    """Cliente aprova ou pede alteração no 3D do cômodo (pendente → aprovado | alteracao_pedida).
    O guard valida a transição e CARIMBA decidido_por/em (M9)."""
    cur = await projeto_member(session, projeto_id)
    if cur.papel != "cliente":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "apenas o cliente decide o 3D")
    room = (
        await session.execute(
            text(
                "select status_3d, nome from public.projeto_ambientes "
                "where id = cast(:a as uuid) and projeto_id = cast(:p as uuid) for update"
            ),
            {"a": str(amb_id), "p": str(projeto_id)},
        )
    ).first()
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cômodo não encontrado")
    if str(room.status_3d) != "pendente":
        raise HTTPException(status.HTTP_409_CONFLICT, "este 3D não está aguardando sua decisão")
    novo = "aprovado" if data.acao == "aprovar" else "alteracao_pedida"
    motivo = data.motivo.strip() if (data.acao == "alteracao" and data.motivo) else None
    try:
        await session.execute(
            text(
                "update public.projeto_ambientes "
                "set status_3d = cast(:s as public.status_aprovacao_3d), motivo_3d = :m "
                "where id = cast(:a as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"s": novo, "m": motivo, "a": str(amb_id), "p": str(projeto_id)},
        )
    except DBAPIError as e:
        sqlstate = getattr(getattr(e, "orig", None), "sqlstate", None)
        if sqlstate == "23514":  # guard: integridade (ex.: motivo exigido)
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "pedir alteração exige um motivo"
            ) from e
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="ambiente_3d.aprovado" if novo == "aprovado" else "ambiente_3d.alteracao_pedida",
        entity_type="projeto_ambiente",
        entity_id=amb_id,
        changed={"status": novo, "motivo": motivo},
        entity_label=room.nome,
        actor_label=await actor_name(session),
    )
    return await _um(session, projeto_id, amb_id)
