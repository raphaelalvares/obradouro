"""Serviço de anexos (Fase 4 — mídia informal de etapa/item).

Pipeline API-only: o byte trafega browser → API → StorageBackend → API → browser (nenhum app fala
com o storage direto). Camadas de autorização espelham o checklist: camada 1 aqui (obra_executor /
obra_member → 403/404 limpos), RLS por obra (2ª camada) e os guards no banco (regra fina + quota).

Órfãos / reconciliação (critério de aceite da Fase 4): as chaves de storage são namespeadas por
anexo (``<tenant>/<obra>/<anexo>/...``). O fluxo grava a LINHA (validada por seq + quota) e SÓ
então os bytes; se o processo morrer no meio, sobram bytes sem linha → ``reconciliar`` varre o
prefixo da obra e expurga as chaves cujo anexo não existe mais no banco. Expurgo definitivo/retenção
é a Fase 8; aqui o delete já remove os bytes (best-effort).
"""

import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import run_cpu
from app.core.config import get_settings
from app.core.database import db_context
from app.core.problems import limite_armazenamento_from_exc
from app.schemas.anexos import AnexoCreate
from app.services.audit import log_event
from app.services.common import actor_name, obra_executor, obra_member, obra_writable
from app.services.imaging import UnsupportedImage, process_image
from app.services.storage import get_storage

settings = get_settings()

_ANEXO_SELECT = """
    select a.id, a.parent_type, a.parent_id, a.nome_arquivo, a.content_type, a.tamanho_bytes,
           a.largura, a.altura, a.legenda, a.criado_por, p.nome as criado_por_nome, a.seq_humano,
           (a.thumb_key is not null) as tem_thumb, a.created_at
    from public.anexos a
    left join public.profiles p on p.id = a.criado_por
"""


def _map_42501(e: DBAPIError) -> HTTPException | None:
    """Guard do banco (camada 2) levanta 42501 → 403 limpo (não vaza como 500)."""
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


def _sanitize_filename(name: str | None, ext: str) -> str:
    """Nome só p/ exibição/download (não entra na chave). Tira caminho e limita o tamanho."""
    base = (name or "").replace("\\", "/").split("/")[-1]
    base = re.sub(r"[\x00-\x1f]", "", base).strip()
    return (base or f"foto.{ext}")[:200]


async def _get_anexo_out(session: AsyncSession, obra_id: uuid.UUID, anexo_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(f"{_ANEXO_SELECT} where a.id = cast(:a as uuid) and a.obra_id = cast(:o as uuid)"),
            {"a": str(anexo_id), "o": str(obra_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "anexo não encontrado")
    return dict(row._mapping)


async def _assert_parent(
    session: AsyncSession, obra_id: uuid.UUID, parent_type: str, parent_id: uuid.UUID
) -> None:
    """Alvo (etapa|item|diário|pendência) existe e é DESTA obra (erro limpo antes do guard)."""
    tbl = {
        "etapa": "etapas",
        "checklist_item": "checklist_itens",
        "diario": "diario_obra",
        "pendencia": "pendencias",
        "diario_tarefa": "diario_tarefas",
    }.get(parent_type, "checklist_itens")
    found = (
        await session.execute(
            text(
                f"select 1 from public.{tbl} "
                "where id = cast(:p as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"p": str(parent_id), "o": str(obra_id)},
        )
    ).first()
    if found is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "alvo do anexo não pertence a esta obra"
        )


# ============================ leitura ============================
async def list_anexos(
    session: AsyncSession, obra_id: uuid.UUID, parent_type: str, parent_id: uuid.UUID
) -> list[dict]:
    await obra_member(session, obra_id)  # qualquer membro ativo vê a galeria
    rows = (
        await session.execute(
            text(
                f"{_ANEXO_SELECT} where a.obra_id = cast(:o as uuid) "
                "and a.parent_type = :pt and a.parent_id = cast(:pid as uuid) "
                "order by a.created_at, a.seq_humano"
            ),
            {"o": str(obra_id), "pt": parent_type, "pid": str(parent_id)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def serve_bytes(
    session: AsyncSession, obra_id: uuid.UUID, anexo_id: uuid.UUID, tipo: str
) -> tuple[bytes, str, str]:
    """Devolve (bytes, content_type, nome) do 'full' ou 'thumb'. Membro ativo (RLS confirma)."""
    await obra_member(session, obra_id)
    meta = (
        await session.execute(
            text(
                "select content_type, storage_key, thumb_key, nome_arquivo "
                "from public.anexos where id = cast(:a as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"a": str(anexo_id), "o": str(obra_id)},
        )
    ).first()
    if meta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "anexo não encontrado")
    if tipo == "thumb" and meta.thumb_key:
        key, ct = meta.thumb_key, "image/jpeg"
    else:
        key, ct = meta.storage_key, meta.content_type
    try:
        data = await get_storage().recuperar(key)
    except FileNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conteúdo do anexo não encontrado") from e
    return data, ct, meta.nome_arquivo


# ============================ upload ============================
async def upload(
    claims: dict, user_id: str, obra_id: uuid.UUID, data: AnexoCreate, arquivo
) -> dict:
    """Upload de foto da obra (caminho de PICO: equipe sincroniza várias fotos offline de uma vez).

    Recebe `claims` (não uma sessão pronta) de propósito: a leitura do upload + o processamento da
    imagem (CPU) rodam FORA de qualquer transação, então NÃO seguramos uma conexão do pool (de 10)
    durante a parte lenta. O processamento vai pra uma thread sob teto de concorrência (`run_cpu`),
    pra não travar o event loop (1 worker) nem estourar a RAM num pico de uploads."""
    # --- transação 1 (curta): autorização + idempotência ANTES de processar (falha rápido) ---
    async with db_context(claims) as session:
        cur = await obra_executor(session, obra_id)  # arquiteto OU prestador (cliente → 403)
        tenant_id = cur.tenant_id

        # idempotência offline: re-POST do MESMO id NESTA obra → devolve o existente (sem re-upload,
        # sem re-audit, sem reprocessar). B4: escopado por obra — id de OUTRA obra/tenant cai no
        # INSERT (e o guard de colisão abaixo resolve), nunca devolve mídia de escopo alheio.
        existing = (
            await session.execute(
                text(
                    f"{_ANEXO_SELECT} "
                    "where a.id = cast(:a as uuid) and a.obra_id = cast(:o as uuid)"
                ),
                {"a": str(data.id), "o": str(obra_id)},
            )
        ).first()
        if existing is not None:
            return dict(existing._mapping)

        await _assert_parent(session, obra_id, data.parent_type, data.parent_id)

    # --- processamento pesado FORA de transação (sem conexão do pool segurada) ---
    raw = await arquivo.read()
    if not raw:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "arquivo vazio")
    if len(raw) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"arquivo acima do limite de {settings.MAX_UPLOAD_MB} MB",
        )
    try:
        proc = await run_cpu(process_image, raw, settings.THUMB_MAX_PX, settings.FULL_MAX_PX)
    except UnsupportedImage as e:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "formato de imagem não suportado"
        ) from e

    nome = _sanitize_filename(getattr(arquivo, "filename", None), proc.full_ext)
    prefix = f"{tenant_id}/{obra_id}/{data.id}"
    full_key = f"{prefix}/full.{proc.full_ext}"
    thumb_key = f"{prefix}/thumb.jpg"
    tamanho = len(proc.full_bytes)

    # --- transação 2 (curta): grava LINHA + BYTES (reabre a conexão só agora) ---
    async with db_context(claims) as session:
        # 1) grava a LINHA (savepoint): triggers de seq + quota validam aqui (P0001 = quota)
        try:
            async with session.begin_nested():
                row = (
                    await session.execute(
                        text(
                            """
                        insert into public.anexos
                          (id, obra_id, tenant_id, parent_type, parent_id, nome_arquivo,
                           content_type, tamanho_bytes, largura, altura, legenda, storage_key,
                           thumb_key, criado_por)
                        values (cast(:id as uuid), cast(:o as uuid), cast(:t as uuid), :pt,
                                cast(:pid as uuid), :nome, :ct, :tam, :larg, :alt, :leg, :sk, :tk,
                                cast(:uid as uuid))
                        returning seq_humano, created_at
                            """
                        ),
                        {
                            "id": str(data.id),
                            "o": str(obra_id),
                            "t": str(tenant_id),
                            "pt": data.parent_type,
                            "pid": str(data.parent_id),
                            "nome": nome,
                            "ct": proc.full_content_type,
                            "tam": tamanho,
                            "larg": proc.largura,
                            "alt": proc.altura,
                            "leg": data.legenda,
                            "sk": full_key,
                            "tk": thumb_key,
                            "uid": str(user_id),
                        },
                    )
                ).first()
        except IntegrityError:  # corrida no mesmo id → devolve o que já existe
            return await _get_anexo_out(session, obra_id, data.id)
        except DBAPIError as e:
            quota = limite_armazenamento_from_exc(e)  # P0001 'limite_armazenamento:...' → 403
            if quota is not None:
                raise quota from e
            raise (_map_42501(e) or e) from e

        # 2) grava os BYTES (após seq/quota validados). Falha → limpa parciais e desfaz a linha.
        storage = get_storage()
        try:
            await storage.guardar(full_key, proc.full_bytes, proc.full_content_type)
            await storage.guardar(thumb_key, proc.thumb_bytes, proc.thumb_content_type)
        except Exception:
            await storage.deletar_prefixo(prefix)  # best-effort (não deixa byte parcial)
            raise  # propaga → db_context faz rollback da linha (sem órfão de linha)

        await log_event(
            session,
            tenant=tenant_id,
            actor_id=user_id,
            obra_id=obra_id,
            action="anexo.criado",
            entity_type="anexo",
            entity_id=data.id,
            changed={
                "parent_type": data.parent_type,
                "parent_id": str(data.parent_id),
                "tamanho_bytes": tamanho,
            },
            entity_label=nome,
            entity_seq=row.seq_humano,
            actor_label=await actor_name(session),
        )
        return await _get_anexo_out(session, obra_id, data.id)


# ============================ editar legenda ============================
async def patch_legenda(
    session: AsyncSession,
    user_id: str,
    obra_id: uuid.UUID,
    anexo_id: uuid.UUID,
    legenda: str | None,
) -> dict:
    """Edita SÓ a legenda (o anexo segue imutável no resto). Executor; guard 0084 refina: prestador
    só edita a própria foto. Não mexe em tamanho_bytes → quota intacta."""
    await obra_executor(session, obra_id)  # arquiteto OU prestador (cliente → 403)
    meta = (
        await session.execute(
            text(
                "select tenant_id, nome_arquivo, seq_humano "
                "from public.anexos where id = cast(:a as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"a": str(anexo_id), "o": str(obra_id)},
        )
    ).first()
    if meta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "anexo não encontrado")
    try:
        await session.execute(
            text(
                "update public.anexos set legenda = :leg "
                "where id = cast(:a as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"leg": legenda, "a": str(anexo_id), "o": str(obra_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session, tenant=meta.tenant_id, actor_id=user_id, obra_id=obra_id, action="anexo.legenda",
        entity_type="anexo", entity_id=anexo_id, changed={"legenda": legenda},
        entity_label=meta.nome_arquivo, entity_seq=meta.seq_humano,
        actor_label=await actor_name(session),
    )
    return await _get_anexo_out(session, obra_id, anexo_id)


# ============================ delete ============================
async def delete_anexo(
    session: AsyncSession, user_id: str, obra_id: uuid.UUID, anexo_id: uuid.UUID
) -> dict:
    await obra_executor(session, obra_id)  # guard 0031 refina: prestador só apaga o próprio
    meta = (
        await session.execute(
            text(
                "select tenant_id, parent_type, parent_id, nome_arquivo, seq_humano "
                "from public.anexos where id = cast(:a as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"a": str(anexo_id), "o": str(obra_id)},
        )
    ).first()
    if meta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "anexo não encontrado")

    # apaga a LINHA primeiro (deixa o guard barrar prestador-de-outro com 42501 → 403)
    try:
        await session.execute(
            text(
                "delete from public.anexos "
                "where id = cast(:a as uuid) and obra_id = cast(:o as uuid)"
            ),
            {"a": str(anexo_id), "o": str(obra_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e

    # depois os bytes (best-effort; se falhar, viram órfãos recolhidos por reconciliar)
    await get_storage().deletar_prefixo(f"{meta.tenant_id}/{obra_id}/{anexo_id}")

    await log_event(
        session,
        tenant=meta.tenant_id,
        actor_id=user_id,
        obra_id=obra_id,
        action="anexo.removido",
        entity_type="anexo",
        entity_id=anexo_id,
        changed={"parent_type": meta.parent_type, "parent_id": str(meta.parent_id)},
        entity_label=meta.nome_arquivo,
        entity_seq=meta.seq_humano,
        actor_label=await actor_name(session),
    )
    return {"deleted": True}


# ============================ reconciliação (housekeeping) ============================
async def reconciliar(session: AsyncSession, user_id: str, obra_id: uuid.UUID) -> dict:
    """Expurga bytes órfãos (sem linha) sob o prefixo da obra. Só arquiteto. Sem audit (limpeza)."""
    cur = await obra_writable(session, obra_id)
    storage = get_storage()
    prefix = f"{cur.tenant_id}/{obra_id}"
    chaves = await storage.listar_chaves(prefix)
    vivos = {
        str(r.id)
        for r in (
            await session.execute(
                text("select id from public.anexos where obra_id = cast(:o as uuid)"),
                {"o": str(obra_id)},
            )
        ).all()
    }
    # chave = '<tenant>/<obra>/<anexo>/<arquivo>' → o anexo é o 3º segmento
    orfaos = {
        partes[2] for k in chaves if len(partes := k.split("/")) >= 3 and partes[2] not in vivos
    }
    removidas = 0
    for aid in orfaos:
        removidas += await storage.deletar_prefixo(f"{prefix}/{aid}")
    return {"orfaos": len(orfaos), "chaves_removidas": removidas}
