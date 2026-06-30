"""Ciclo de revisões: subir (arquiteto), verbos do cliente (aprovar/recusar/pedir alteração),
contador AO VIVO, e arquivos da revisão (PDF/imagem) pelo StorageBackend.

Limite de alterações = `projetos.revisoes_incluidas` (parâmetro do arquiteto, NÃO eixo de plano).
"além do incluído" = numero > revisoes_incluidas (na leitura, sem coluna congelada); o fato
do momento fica no audit. R0 = entrega base (0 alterações); R1,R2… = alterações.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import run_cpu
from app.core.config import get_settings
from app.core.problems import limite_armazenamento_from_exc
from app.schemas.revisoes import RevisaoCreate, RevisaoDecisao
from app.services.audit import log_event
from app.services.common import actor_name, projeto_member, projeto_writable
from app.services.projeto_media import UnsupportedUpload, prepare_media, sanitize_filename
from app.services.storage import get_storage

settings = get_settings()

_ARQ_SELECT = """
    select id, nome_arquivo, content_type, tamanho_bytes, largura, altura, is_pdf,
           (thumb_key is not null) as tem_thumb, opcao, created_at
    from public.revisao_arquivos
"""

_ACAO_STATUS = {
    "aprovar": "aprovado",
    "alteracao": "alteracao_pedida",
    "recusar": "recusado",
    "escolher": "aprovado",  # escolher uma opção = aprovar a revisão de opções
}
_ACAO_EVENTO = {
    "aprovar": "revisao.aprovada",
    "alteracao": "revisao.alteracao_pedida",
    "recusar": "revisao.recusada",
    "escolher": "revisao.opcao_escolhida",
}


def _map_42501(e: DBAPIError) -> HTTPException | None:
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


def _alem(numero: int, incluidas: int | None) -> bool:
    return incluidas is not None and numero > incluidas


async def _arquivos_por_revisao(session: AsyncSession, projeto_id: uuid.UUID) -> dict:
    rows = (
        await session.execute(
            text(
                f"{_ARQ_SELECT.replace('select id,', 'select revisao_id, id,')} "
                "where projeto_id = cast(:p as uuid) order by created_at"
            ),
            {"p": str(projeto_id)},
        )
    ).all()
    by_rev: dict = {}
    for r in rows:
        d = dict(r._mapping)
        by_rev.setdefault(d.pop("revisao_id"), []).append(d)
    return by_rev


def _rev_out(row, incluidas: int | None, arquivos: list) -> dict:
    d = dict(row._mapping)
    d["alem_do_incluido"] = _alem(d["numero"], incluidas)
    d["arquivos"] = arquivos
    return d


_REV_SELECT = """
    select r.id, r.numero, r.titulo, r.status, r.motivo, r.decidido_por,
           p.nome as decidido_por_nome, r.decidido_em, r.opcao_escolhida, r.seq_humano, r.created_at
    from public.revisoes r
    left join public.profiles p on p.id = r.decidido_por
"""


# ============================ leitura ============================
async def list_revisoes(session: AsyncSession, projeto_id: uuid.UUID) -> list[dict]:
    cur = await projeto_member(session, projeto_id)
    revs = (
        await session.execute(
            text(f"{_REV_SELECT} where r.projeto_id = cast(:p as uuid) order by r.numero"),
            {"p": str(projeto_id)},
        )
    ).all()
    arqs = await _arquivos_por_revisao(session, projeto_id)
    return [_rev_out(r, cur.revisoes_incluidas, arqs.get(r.id, [])) for r in revs]


async def get_revisao(
    session: AsyncSession, projeto_id: uuid.UUID, revisao_id: uuid.UUID
) -> dict:
    cur = await projeto_member(session, projeto_id)
    row = (
        await session.execute(
            text(
                f"{_REV_SELECT} where r.id = cast(:r as uuid) and r.projeto_id = cast(:p as uuid)"
            ),
            {"r": str(revisao_id), "p": str(projeto_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "revisão não encontrada")
    arqs = await _arquivos_por_revisao(session, projeto_id)
    return _rev_out(row, cur.revisoes_incluidas, arqs.get(row.id, []))


async def contador(session: AsyncSession, projeto_id: uuid.UUID) -> dict:
    cur = await projeto_member(session, projeto_id)
    max_num = (
        await session.execute(
            text("select max(numero) from public.revisoes where projeto_id = cast(:p as uuid)"),
            {"p": str(projeto_id)},
        )
    ).scalar()
    usadas = int(max_num) if max_num is not None else 0  # nº de alterações já feitas (R0 = 0)
    incluidas = cur.revisoes_incluidas
    controla = incluidas is not None
    alem_count = 0
    if controla:
        alem_count = (
            await session.execute(
                text(
                    "select count(*) from public.revisoes "
                    "where projeto_id = cast(:p as uuid) and numero > :inc"
                ),
                {"p": str(projeto_id), "inc": incluidas},
            )
        ).scalar_one()
    return {
        "controla": controla,
        "incluidas": incluidas,
        "usadas": usadas,
        "restantes": max(0, incluidas - usadas) if controla else None,
        "alem_count": int(alem_count),
    }


# ============================ subir (arquiteto) ============================
async def subir(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, data: RevisaoCreate
) -> dict:
    cur = await projeto_writable(session, projeto_id)  # camada 1: só arquiteto
    try:
        row = (
            await session.execute(
                text(
                    """
                    select id, numero, seq_humano
                    from public.subir_revisao(cast(:id as uuid), cast(:p as uuid), :titulo)
                    """
                ),
                {"id": str(data.id), "p": str(projeto_id), "titulo": data.titulo},
            )
        ).first()
    except DBAPIError as e:
        msg = str(getattr(e, "orig", e))
        if "revisao_pendente_existe" in msg:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "já existe uma revisão pendente — aguarde a decisão do cliente",
            ) from e
        raise (_map_42501(e) or e) from e

    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="revisao.criada",
        entity_type="revisao",
        entity_id=data.id,
        changed={
            "numero": row.numero,
            "alem_do_incluido": _alem(row.numero, cur.revisoes_incluidas),
        },
        entity_label=data.titulo or f"R{row.numero}",
        entity_seq=row.seq_humano,
        actor_label=await actor_name(session),
    )
    return await get_revisao(session, projeto_id, data.id)


# ============================ verbos do cliente ============================
async def decidir(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    revisao_id: uuid.UUID,
    data: RevisaoDecisao,
) -> dict:
    cur = await projeto_member(session, projeto_id)
    if cur.papel != "cliente":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "apenas o cliente decide a revisão")
    if data.acao in ("alteracao", "recusar") and not (data.motivo and data.motivo.strip()):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "informe o motivo da alteração/recusa"
        )
    novo_status = _ACAO_STATUS[data.acao]
    com_motivo = data.acao in ("alteracao", "recusar")
    motivo = data.motivo.strip() if (com_motivo and data.motivo) else None
    opcao = data.opcao_escolhida if data.acao == "escolher" else None

    locked = (
        await session.execute(
            text(
                "select status, numero, titulo, seq_humano from public.revisoes "
                "where id = cast(:r as uuid) and projeto_id = cast(:p as uuid) for update"
            ),
            {"r": str(revisao_id), "p": str(projeto_id)},
        )
    ).first()
    if locked is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "revisão não encontrada")
    if locked.status != "pendente":
        raise HTTPException(status.HTTP_409_CONFLICT, "esta revisão já foi decidida")

    # Revisão "de opções" (layouts 1-de-N): tem arquivos com opcao não-nula. Nela, aprovar EXIGE
    # escolher uma das opções (alteração/recusa seguem livres). Sem opções, "escolher" não cabe.
    tem_opcoes = bool(
        (
            await session.execute(
                text(
                    "select 1 from public.revisao_arquivos "
                    "where revisao_id = cast(:r as uuid) and opcao is not null limit 1"
                ),
                {"r": str(revisao_id)},
            )
        ).first()
    )
    if data.acao == "aprovar" and tem_opcoes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "esta revisão tem opções de layout — escolha uma para aprovar",
        )
    if data.acao == "escolher":
        if not tem_opcoes:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "esta revisão não tem opções para escolher"
            )
        existe = (
            await session.execute(
                text(
                    "select 1 from public.revisao_arquivos "
                    "where revisao_id = cast(:r as uuid) and opcao = :oe limit 1"
                ),
                {"r": str(revisao_id), "oe": opcao},
            )
        ).first()
        if existe is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "opção escolhida inválida")
    try:
        await session.execute(
            text(
                """
                update public.revisoes set
                  status = cast(:s as public.status_revisao),
                  motivo = :motivo,
                  opcao_escolhida = :oe,
                  decidido_por = (select auth.uid()),
                  decidido_em = now()
                where id = cast(:r as uuid)
                """
            ),
            {"s": novo_status, "motivo": motivo, "oe": opcao, "r": str(revisao_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action=_ACAO_EVENTO[data.acao],
        entity_type="revisao",
        entity_id=revisao_id,
        changed={"de": locked.status, "para": novo_status, "motivo": motivo, "opcao": opcao},
        entity_label=locked.titulo or f"R{locked.numero}",
        entity_seq=locked.seq_humano,
        actor_label=await actor_name(session),
    )
    return await get_revisao(session, projeto_id, revisao_id)


# ============================ arquivos da revisão ============================
async def _assert_revisao(session: AsyncSession, projeto_id: uuid.UUID, revisao_id: uuid.UUID):
    found = (
        await session.execute(
            text(
                "select 1 from public.revisoes "
                "where id = cast(:r as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"r": str(revisao_id), "p": str(projeto_id)},
        )
    ).first()
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "revisão não encontrada")


async def list_arquivos(
    session: AsyncSession, projeto_id: uuid.UUID, revisao_id: uuid.UUID
) -> list[dict]:
    await projeto_member(session, projeto_id)
    await _assert_revisao(session, projeto_id, revisao_id)
    rows = (
        await session.execute(
            text(f"{_ARQ_SELECT} where revisao_id = cast(:r as uuid) order by created_at"),
            {"r": str(revisao_id)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def upload_arquivo(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    revisao_id: uuid.UUID,
    arquivo_id: uuid.UUID,
    arquivo,
    opcao: int | None = None,
) -> dict:
    cur = await projeto_writable(session, projeto_id)  # só arquiteto anexa arquivo de revisão
    await _assert_revisao(session, projeto_id, revisao_id)
    if opcao is not None and not 1 <= opcao <= 9:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "opção deve ser entre 1 e 9")

    # B4: idempotência escopada por projeto (id de outro escopo cai no INSERT; vide except abaixo)
    existing = (
        await session.execute(
            text(f"{_ARQ_SELECT} where id = cast(:a as uuid) and projeto_id = cast(:p as uuid)"),
            {"a": str(arquivo_id), "p": str(projeto_id)},
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
        media = await run_cpu(
            prepare_media, raw, settings.THUMB_MAX_PX, settings.FULL_MAX_PX, allow_pdf=True
        )
    except UnsupportedUpload as e:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "arquivo deve ser imagem ou PDF"
        ) from e

    nome = sanitize_filename(getattr(arquivo, "filename", None), media["full_ext"])
    prefix = f"{cur.tenant_id}/projetos/{projeto_id}/revisoes/{revisao_id}/{arquivo_id}"
    full_key = f"{prefix}/{'file.pdf' if media['is_pdf'] else 'full.' + media['full_ext']}"
    thumb_key = None if media["is_pdf"] else f"{prefix}/thumb.jpg"
    tamanho = len(media["full_bytes"])

    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    insert into public.revisao_arquivos
                      (id, revisao_id, projeto_id, tenant_id, nome_arquivo, content_type,
                       tamanho_bytes, largura, altura, is_pdf, opcao, storage_key, thumb_key,
                       criado_por)
                    values (cast(:id as uuid), cast(:r as uuid), cast(:p as uuid), cast(:t as uuid),
                            :nome, :ct, :tam, :larg, :alt, :pdf, :opcao, :sk, :tk,
                            cast(:uid as uuid))
                    """
                ),
                {
                    "id": str(arquivo_id),
                    "r": str(revisao_id),
                    "p": str(projeto_id),
                    "t": str(cur.tenant_id),
                    "nome": nome,
                    "ct": media["full_content_type"],
                    "tam": tamanho,
                    "larg": media["largura"],
                    "alt": media["altura"],
                    "pdf": media["is_pdf"],
                    "opcao": opcao,
                    "sk": full_key,
                    "tk": thumb_key,
                    "uid": str(user_id),
                },
            )
    except IntegrityError as e:
        # corrida no MESMO id (mesmo projeto) → devolve o existente. B4: se o id colide com row de
        # OUTRO escopo (RLS oculta → .first() seria None), responde 409 limpo em vez de 500/oráculo.
        sql = f"{_ARQ_SELECT} where id = cast(:a as uuid) and projeto_id = cast(:p as uuid)"
        existing = (
            await session.execute(text(sql), {"a": str(arquivo_id), "p": str(projeto_id)})
        ).first()
        if existing is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "id de arquivo já em uso") from e
        return dict(existing._mapping)
    except DBAPIError as e:
        quota = limite_armazenamento_from_exc(e)
        if quota is not None:
            raise quota from e
        raise (_map_42501(e) or e) from e

    storage = get_storage()
    try:
        await storage.guardar(full_key, media["full_bytes"], media["full_content_type"])
        if thumb_key:
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
        action="revisao.arquivo_anexado",
        entity_type="revisao_arquivo",
        entity_id=arquivo_id,
        changed={
            "revisao_id": str(revisao_id),
            "tamanho_bytes": tamanho,
            "is_pdf": media["is_pdf"],
        },
        entity_label=nome,
        actor_label=await actor_name(session),
    )
    return dict(
        (
            await session.execute(
                text(f"{_ARQ_SELECT} where id = cast(:a as uuid)"), {"a": str(arquivo_id)}
            )
        ).first()._mapping
    )


async def serve_arquivo(
    session: AsyncSession,
    projeto_id: uuid.UUID,
    revisao_id: uuid.UUID,
    arquivo_id: uuid.UUID,
    tipo: str,
) -> tuple[bytes, str, str]:
    await projeto_member(session, projeto_id)
    meta = (
        await session.execute(
            text(
                "select content_type, storage_key, thumb_key, nome_arquivo "
                "from public.revisao_arquivos "
                "where id = cast(:a as uuid) and revisao_id = cast(:r as uuid) "
                "and projeto_id = cast(:p as uuid)"
            ),
            {"a": str(arquivo_id), "r": str(revisao_id), "p": str(projeto_id)},
        )
    ).first()
    if meta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "arquivo não encontrado")
    if tipo == "thumb":
        if not meta.thumb_key:  # PDF não tem thumb → 404 (não cair no full)
            raise HTTPException(status.HTTP_404_NOT_FOUND, "sem miniatura")
        key, ct = meta.thumb_key, "image/jpeg"
    else:
        key, ct = meta.storage_key, meta.content_type
    try:
        data = await get_storage().recuperar(key)
    except FileNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conteúdo não encontrado") from e
    return data, ct, meta.nome_arquivo


async def delete_arquivo(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    revisao_id: uuid.UUID,
    arquivo_id: uuid.UUID,
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    meta = (
        await session.execute(
            text(
                "select nome_arquivo from public.revisao_arquivos "
                "where id = cast(:a as uuid) and revisao_id = cast(:r as uuid) "
                "and projeto_id = cast(:p as uuid)"
            ),
            {"a": str(arquivo_id), "r": str(revisao_id), "p": str(projeto_id)},
        )
    ).first()
    if meta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "arquivo não encontrado")
    try:
        await session.execute(
            text("delete from public.revisao_arquivos where id = cast(:a as uuid)"),
            {"a": str(arquivo_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await get_storage().deletar_prefixo(
        f"{cur.tenant_id}/projetos/{projeto_id}/revisoes/{revisao_id}/{arquivo_id}"
    )
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="revisao.arquivo_removido",
        entity_type="revisao_arquivo",
        entity_id=arquivo_id,
        changed={"revisao_id": str(revisao_id)},
        entity_label=meta.nome_arquivo,
        actor_label=await actor_name(session),
    )
    return {"deleted": True}
