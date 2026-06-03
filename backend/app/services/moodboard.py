"""Moodboard do projeto: seções + itens (imagens de referência). Arquiteto cura; cliente vê.
Itens reusam o StorageBackend/imaging (só imagem, sem PDF)."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.problems import limite_armazenamento_from_exc
from app.schemas.moodboard import SecaoCreate, SecaoUpdate
from app.services.audit import log_event
from app.services.common import actor_name, projeto_member, projeto_writable
from app.services.projeto_media import UnsupportedUpload, prepare_media, sanitize_filename
from app.services.storage import get_storage

settings = get_settings()

_ITEM_SELECT = """
    select id, secao_id, legenda, nome_arquivo, content_type, tamanho_bytes, largura, altura,
           ordem, seq_humano, (thumb_key is not null) as tem_thumb, created_at
    from public.moodboard_itens
"""


def _map_42501(e: DBAPIError) -> HTTPException | None:
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


# ============================ seções ============================
async def list_secoes(session: AsyncSession, projeto_id: uuid.UUID) -> list[dict]:
    await projeto_member(session, projeto_id)
    rows = (
        await session.execute(
            text(
                "select id, nome, ordem, created_at from public.moodboard_secoes "
                "where projeto_id = cast(:p as uuid) order by ordem, created_at"
            ),
            {"p": str(projeto_id)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def create_secao(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, data: SecaoCreate
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    try:
        await session.execute(
            text(
                """
                insert into public.moodboard_secoes
                    (id, projeto_id, tenant_id, nome, ordem, created_by)
                values (cast(:id as uuid), cast(:p as uuid), cast(:t as uuid), :nome, :ordem,
                        cast(:uid as uuid))
                on conflict (id) do nothing
                """
            ),
            {
                "id": str(data.id),
                "p": str(projeto_id),
                "t": str(cur.tenant_id),
                "nome": data.nome,
                "ordem": data.ordem,
                "uid": str(user_id),
            },
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="moodboard.secao_criada",
        entity_type="moodboard_secao",
        entity_id=data.id,
        entity_label=data.nome,
        actor_label=await actor_name(session),
    )
    row = (
        await session.execute(
            text(
                "select id, nome, ordem, created_at from public.moodboard_secoes "
                "where id = cast(:id as uuid)"
            ),
            {"id": str(data.id)},
        )
    ).first()
    return dict(row._mapping)


async def update_secao(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    secao_id: uuid.UUID,
    data: SecaoUpdate,
) -> dict:
    await projeto_writable(session, projeto_id)
    sets, params = [], {"id": str(secao_id), "p": str(projeto_id)}
    if data.nome is not None:
        sets.append("nome = :nome")
        params["nome"] = data.nome
    if data.ordem is not None:
        sets.append("ordem = :ordem")
        params["ordem"] = data.ordem
    if sets:
        try:
            res = (
                await session.execute(
                    text(
                        f"update public.moodboard_secoes set {', '.join(sets)} "
                        "where id = cast(:id as uuid) and projeto_id = cast(:p as uuid) "
                        "returning id"
                    ),
                    params,
                )
            ).first()
        except DBAPIError as e:
            raise (_map_42501(e) or e) from e
        if res is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "seção não encontrada")
    row = (
        await session.execute(
            text(
                "select id, nome, ordem, created_at from public.moodboard_secoes "
                "where id = cast(:id as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"id": str(secao_id), "p": str(projeto_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "seção não encontrada")
    return dict(row._mapping)


async def delete_secao(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, secao_id: uuid.UUID
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    res = (
        await session.execute(
            text(
                "delete from public.moodboard_secoes "
                "where id = cast(:id as uuid) and projeto_id = cast(:p as uuid) returning nome"
            ),
            {"id": str(secao_id), "p": str(projeto_id)},
        )
    ).first()
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "seção não encontrada")
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="moodboard.secao_removida",
        entity_type="moodboard_secao",
        entity_id=secao_id,
        entity_label=res.nome,
        actor_label=await actor_name(session),
    )
    return {"deleted": True}


# ============================ itens ============================
async def list_itens(session: AsyncSession, projeto_id: uuid.UUID) -> list[dict]:
    await projeto_member(session, projeto_id)
    rows = (
        await session.execute(
            text(f"{_ITEM_SELECT} where projeto_id = cast(:p as uuid) order by ordem, seq_humano"),
            {"p": str(projeto_id)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def upload_item(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    item_id: uuid.UUID,
    secao_id: uuid.UUID | None,
    legenda: str | None,
    arquivo,
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    existing = (
        await session.execute(
            text(f"{_ITEM_SELECT} where id = cast(:i as uuid)"), {"i": str(item_id)}
        )
    ).first()
    if existing is not None:
        return dict(existing._mapping)

    raw = await arquivo.read()
    if not raw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "arquivo vazio")
    if len(raw) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"arquivo acima do limite de {settings.MAX_UPLOAD_MB} MB",
        )
    try:
        media = prepare_media(raw, settings.THUMB_MAX_PX, settings.FULL_MAX_PX, allow_pdf=False)
    except UnsupportedUpload as e:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "moodboard aceita só imagem"
        ) from e

    nome = sanitize_filename(getattr(arquivo, "filename", None), media["full_ext"])
    prefix = f"{cur.tenant_id}/projetos/{projeto_id}/moodboard/{item_id}"
    full_key = f"{prefix}/full.{media['full_ext']}"
    thumb_key = f"{prefix}/thumb.jpg"
    tamanho = len(media["full_bytes"])

    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    insert into public.moodboard_itens
                      (id, projeto_id, tenant_id, secao_id, legenda, nome_arquivo, content_type,
                       tamanho_bytes, largura, altura, storage_key, thumb_key, criado_por)
                    values (cast(:id as uuid), cast(:p as uuid), cast(:t as uuid),
                            cast(:secao as uuid), :legenda, :nome, :ct, :tam, :larg, :alt,
                            :sk, :tk, cast(:uid as uuid))
                    """
                ),
                {
                    "id": str(item_id),
                    "p": str(projeto_id),
                    "t": str(cur.tenant_id),
                    "secao": str(secao_id) if secao_id else None,
                    "legenda": legenda,
                    "nome": nome,
                    "ct": media["full_content_type"],
                    "tam": tamanho,
                    "larg": media["largura"],
                    "alt": media["altura"],
                    "sk": full_key,
                    "tk": thumb_key,
                    "uid": str(user_id),
                },
            )
    except IntegrityError:
        return dict(
            (
                await session.execute(
                    text(f"{_ITEM_SELECT} where id = cast(:i as uuid)"), {"i": str(item_id)}
                )
            ).first()._mapping
        )
    except DBAPIError as e:
        quota = limite_armazenamento_from_exc(e)
        if quota is not None:
            raise quota from e
        raise (_map_42501(e) or e) from e

    storage = get_storage()
    try:
        await storage.guardar(full_key, media["full_bytes"], media["full_content_type"])
        await storage.guardar(thumb_key, media["thumb_bytes"], "image/jpeg")
    except Exception:
        await storage.deletar_prefixo(prefix)
        raise

    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="moodboard.item_adicionado",
        entity_type="moodboard_item",
        entity_id=item_id,
        changed={"tamanho_bytes": tamanho},
        entity_label=legenda or nome,
        actor_label=await actor_name(session),
    )
    return dict(
        (
            await session.execute(
                text(f"{_ITEM_SELECT} where id = cast(:i as uuid)"), {"i": str(item_id)}
            )
        ).first()._mapping
    )


async def serve_item(
    session: AsyncSession, projeto_id: uuid.UUID, item_id: uuid.UUID, tipo: str
) -> tuple[bytes, str, str]:
    await projeto_member(session, projeto_id)
    meta = (
        await session.execute(
            text(
                "select content_type, storage_key, thumb_key, nome_arquivo "
                "from public.moodboard_itens "
                "where id = cast(:i as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"i": str(item_id), "p": str(projeto_id)},
        )
    ).first()
    if meta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item não encontrado")
    if tipo == "thumb" and meta.thumb_key:
        key, ct = meta.thumb_key, "image/jpeg"
    else:
        key, ct = meta.storage_key, meta.content_type
    try:
        data = await get_storage().recuperar(key)
    except FileNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conteúdo não encontrado") from e
    return data, ct, meta.nome_arquivo


async def delete_item(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, item_id: uuid.UUID
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    meta = (
        await session.execute(
            text(
                "select nome_arquivo, legenda from public.moodboard_itens "
                "where id = cast(:i as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"i": str(item_id), "p": str(projeto_id)},
        )
    ).first()
    if meta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item não encontrado")
    try:
        await session.execute(
            text("delete from public.moodboard_itens where id = cast(:i as uuid)"),
            {"i": str(item_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await get_storage().deletar_prefixo(
        f"{cur.tenant_id}/projetos/{projeto_id}/moodboard/{item_id}"
    )
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="moodboard.item_removido",
        entity_type="moodboard_item",
        entity_id=item_id,
        entity_label=meta.legenda or meta.nome_arquivo,
        actor_label=await actor_name(session),
    )
    return {"deleted": True}
