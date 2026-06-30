"""Pipeline do projeto (linha do tempo de 9 etapas fixas). Ver migration 0097.

`listar` é para arquiteto E cliente (membros): semeia as etapas no read do arquiteto, lê a tabela e
DERIVA `acao_pendente` de cada gate cruzando o estado vivo (revisão pendente / orçamento enviado /
orçamento aprovado), via a RPC definer `pipeline_gates` (o cliente não lê orcamento_versoes direto).
`atualizar_etapa` é do arquiteto; `decidir_iniciar_obra` é do cliente (RPC definer).
"""

import json
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import run_cpu
from app.core.config import get_settings
from app.core.problems import limite_armazenamento_from_exc
from app.schemas.pipeline import EtapaLinkCreate
from app.services import ambientes_projeto, manual_projeto
from app.services.audit import log_event
from app.services.common import actor_name, projeto_member, projeto_writable
from app.services.projeto_media import UnsupportedUpload, prepare_media, sanitize_filename
from app.services.storage import get_storage

settings = get_settings()

# material (arquivo|link) por etapa — espelha revisao_arquivos; bytes no StorageBackend (ver 0099)
_ANEXO_SELECT = """
    select id, etapa, tipo, label, url, nome_arquivo, content_type, tamanho_bytes, is_pdf,
           (thumb_key is not null) as tem_thumb, ordem, created_at
    from public.projeto_etapa_anexos
"""

# (código, rótulo pt-BR, gate). Ordem = posição na lista (1..9). FIXO (decisão do usuário).
_ETAPAS: list[tuple[str, str, str | None]] = [
    ("medicao", "Agendamento de medição", None),
    ("base", "Planta base", None),
    ("layouts", "Layouts", "revisao"),
    ("projeto_3d", "Projeto 3D", None),
    ("apresentacao", "Apresentação", None),
    ("aprovacao", "Aprovação do projeto", "revisao"),
    ("manual", "Manual do proprietário", None),
    ("orcamento", "Orçamento da obra (EVF)", "proposta"),
    ("iniciar_obra", "Início da obra", "iniciar_obra"),
]
ROTULOS = {c: r for c, r, _ in _ETAPAS}
GATES = {c: g for c, _, g in _ETAPAS}
ORDEM = {c: i + 1 for i, (c, _, _) in enumerate(_ETAPAS)}
_STATUS_VALIDOS = {"a_fazer", "em_andamento", "aguardando_cliente", "concluida"}


def _acao_pendente(codigo: str, etapa: dict, gates: dict) -> bool:
    """Há ação do cliente esperando neste gate? (deriva do estado vivo)."""
    gate = GATES.get(codigo)
    if gate == "revisao":
        return bool(gates.get("rev_pendente"))
    if gate == "proposta":
        return bool(gates.get("orc_pendente"))
    if gate == "iniciar_obra":
        return etapa.get("decisao") is None and bool(gates.get("orc_aprovado"))
    return False


def _ambiente_3d_pendente(rooms: list | None) -> bool:
    """projeto_3d: há algum cômodo aguardando a decisão do cliente?"""
    return any((r or {}).get("status_3d") == "pendente" for r in (rooms or []))


def _monta(
    etapa: dict,
    gates: dict,
    anexos: list | None = None,
    ambientes_3d: list | None = None,
    manual_itens: list | None = None,
) -> dict:
    codigo = etapa["etapa"]
    acao = (
        _ambiente_3d_pendente(ambientes_3d)
        if codigo == "projeto_3d"
        else _acao_pendente(codigo, etapa, gates)
    )
    return {
        "etapa": codigo,
        "rotulo": ROTULOS.get(codigo, codigo),
        "ordem": etapa.get("ordem") or ORDEM.get(codigo, 99),
        "status": etapa.get("status") or "a_fazer",
        "data_prevista": etapa.get("data_prevista"),
        "concluida_em": etapa.get("concluida_em"),
        "decisao": etapa.get("decisao"),
        "observacao": etapa.get("observacao"),
        "gate": GATES.get(codigo),
        "acao_pendente": acao,
        "anexos": anexos or [],
        "ambientes_3d": ambientes_3d or [],
        "manual_itens": manual_itens or [],
    }


async def _anexos_por_etapa(session: AsyncSession, projeto_id: uuid.UUID) -> dict:
    # material genérico da etapa = sem alvo por-item (ambiente_id E manual_item_id nulos); o
    # material POR CÔMODO (projeto_3d) e POR ITEM do manual é servido à parte por listar_3d /
    # listar_manual (senão duplicaria na seção genérica).
    rows = (
        await session.execute(
            text(
                f"{_ANEXO_SELECT} where projeto_id = cast(:p as uuid) "
                "and ambiente_id is null and manual_item_id is null order by ordem, created_at"
            ),
            {"p": str(projeto_id)},
        )
    ).all()
    by: dict = {}
    for r in rows:
        d = dict(r._mapping)
        d["etapa"] = str(d["etapa"])  # enum → str (chave = código da etapa)
        by.setdefault(d["etapa"], []).append(d)
    return by


async def listar(session: AsyncSession, projeto_id: uuid.UUID) -> dict:
    await projeto_member(session, projeto_id)  # 404 se não-membro
    # semeadura preguiçosa: qualquer membro ativo semeia (a RPC gateia por meu_papel_projeto) — o
    # cliente também vê a timeline materializada num projeto antigo que o arquiteto não abriu.
    await session.execute(
        text("select public.garantir_etapas_projeto(cast(:p as uuid))"),
        {"p": str(projeto_id)},
    )
    rows = (
        await session.execute(
            text(
                """select etapa, ordem, status, data_prevista, concluida_em, decisao, observacao
                   from public.projeto_etapas where projeto_id = cast(:p as uuid) order by ordem"""
            ),
            {"p": str(projeto_id)},
        )
    ).all()
    # fallback p/ projeto antigo não semeado (cliente lendo antes do arquiteto): defaults read-only
    etapas = (
        [dict(r._mapping) for r in rows]
        if rows
        else [{"etapa": c, "ordem": ORDEM[c], "status": "a_fazer"} for c, _, _ in _ETAPAS]
    )
    raw = (
        await session.execute(
            text("select public.pipeline_gates(cast(:p as uuid))"), {"p": str(projeto_id)}
        )
    ).scalar_one_or_none()
    gates = (json.loads(raw) if isinstance(raw, str) else raw) or {}
    anx = await _anexos_por_etapa(session, projeto_id)
    ambientes_3d = await ambientes_projeto.listar_3d(session, projeto_id)  # cômodos (projeto_3d)
    manual_itens = await manual_projeto.listar_manual(session, projeto_id)  # itens (manual)
    out = [
        _monta(
            e,
            gates,
            anx.get(e["etapa"], []),
            ambientes_3d if e["etapa"] == "projeto_3d" else None,
            manual_itens if e["etapa"] == "manual" else None,
        )
        for e in etapas
    ]
    atual = next(
        (e["etapa"] for e in out if e["status"] != "concluida"),
        out[-1]["etapa"] if out else None,
    )
    return {"etapas": out, "etapa_atual": atual}


async def atualizar_etapa(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    etapa: str,
    *,
    novo_status: str | None = None,
    data_prevista=None,
    observacao: str | None = None,
    set_data: bool = False,
    set_obs: bool = False,
) -> dict:
    """Arquiteto avança a etapa. `set_data`/`set_obs` distinguem 'não enviado' de 'enviado None'."""
    cur = await projeto_writable(session, projeto_id)
    if etapa not in ROTULOS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "etapa inexistente")
    sets, params = [], {"p": str(projeto_id), "e": etapa}
    if novo_status is not None:
        if novo_status not in _STATUS_VALIDOS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "status inválido")
        sets.append("status = cast(:s as public.status_etapa)")
        params["s"] = novo_status
        sets.append("concluida_em = case when :s = 'concluida' then now() else null end")
    if set_data:
        sets.append("data_prevista = :d")
        params["d"] = data_prevista
    if set_obs:
        sets.append("observacao = :o")
        params["o"] = observacao
    if sets:
        # garante a etapa semeada (idempotente) antes de atualizar — cobre projeto antigo
        await session.execute(
            text("select public.garantir_etapas_projeto(cast(:p as uuid))"),
            {"p": str(projeto_id)},
        )
        await session.execute(
            text(
                f"update public.projeto_etapas set {', '.join(sets)} "
                "where projeto_id = cast(:p as uuid) "
                "and etapa = cast(:e as public.etapa_projeto)"
            ),
            params,
        )
        await log_event(
            session,
            tenant=cur.tenant_id,
            actor_id=user_id,
            obra_id=None,
            projeto_id=projeto_id,
            action="projeto.etapa_atualizada",
            entity_type="projeto",
            entity_id=projeto_id,
            changed={k: (str(v) if k in ("d",) else v) for k, v in params.items()
                     if k not in ("p", "e")},
            entity_label=cur.nome,
            entity_seq=cur.seq_humano,
            actor_label=await actor_name(session),
        )
    return await listar(session, projeto_id)


async def decidir_iniciar_obra(
    session: AsyncSession, projeto_id: uuid.UUID, decisao: str
) -> dict:
    """Cliente decide iniciar a obra (sim/não). RPC definer valida papel/expiry e audita. Mapeia os
    erros da RPC (sqlstate) p/ HTTP — espelha decidir_proposta (orcamentos.py)."""
    try:
        await session.execute(
            text("select public.decidir_iniciar_obra(cast(:p as uuid), :d)"),
            {"p": str(projeto_id), "d": decisao},
        )
    except DBAPIError as e:
        sqlstate = getattr(getattr(e, "orig", None), "sqlstate", None)
        if sqlstate == "42501":  # não é cliente ativo (ou acesso vencido)
            raise HTTPException(status.HTTP_403_FORBIDDEN, "apenas o cliente decide") from e
        if sqlstate == "P0002":  # pipeline ainda não preparado p/ este projeto
            raise HTTPException(status.HTTP_404_NOT_FOUND, "etapa não encontrada") from e
        if sqlstate == "22023":
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "decisão inválida") from e
        raise
    return await listar(session, projeto_id)


# ============================ material da etapa (arquivo | link) ============================
def _map_42501(e: DBAPIError) -> HTTPException | None:
    """Guard/RLS '42501' (ex.: arquiteto perdeu acesso no meio do request) → 403, não 500."""
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


def _valida_etapa(etapa: str) -> None:
    if etapa not in ROTULOS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "etapa inexistente")


async def _semear(session: AsyncSession, projeto_id: uuid.UUID) -> None:
    # a FK do anexo aponta pra linha (projeto, etapa) de projeto_etapas → garante semeada antes
    await session.execute(
        text("select public.garantir_etapas_projeto(cast(:p as uuid))"),
        {"p": str(projeto_id)},
    )


async def _valida_ambiente(
    session: AsyncSession, projeto_id: uuid.UUID, ambiente_id: uuid.UUID | None
) -> None:
    """Material por cômodo (projeto_3d): o ambiente_id tem de ser um cômodo deste projeto E estar
    editável (rascunho/alteracao_pedida). Não se mexe no material de um 3D já enviado/aprovado —
    senão o cliente veria algo diferente do que decidiu (defesa em profundidade do front)."""
    if ambiente_id is None:
        return
    room = (
        await session.execute(
            text(
                "select status_3d from public.projeto_ambientes "
                "where id = cast(:a as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"a": str(ambiente_id), "p": str(projeto_id)},
        )
    ).first()
    if room is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "cômodo não encontrado")
    if str(room.status_3d) not in ("rascunho", "alteracao_pedida"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "cômodo já enviado; recolha-o antes de mexer no material"
        )


async def _valida_manual_item(
    session: AsyncSession, projeto_id: uuid.UUID, manual_item_id: uuid.UUID | None
) -> None:
    """Material por item do manual (etapa manual): o manual_item_id tem de ser item deste projeto.
    Sem trava de status — o manual é editável a qualquer momento (read-only só p/ o cliente)."""
    if manual_item_id is None:
        return
    item = (
        await session.execute(
            text(
                "select 1 from public.projeto_manual_itens "
                "where id = cast(:m as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"m": str(manual_item_id), "p": str(projeto_id)},
        )
    ).first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item do manual não encontrado")


async def upload_etapa_arquivo(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    etapa: str,
    anexo_id: uuid.UUID,
    arquivo,
    label: str | None = None,
    ambiente_id: uuid.UUID | None = None,
    manual_item_id: uuid.UUID | None = None,
) -> dict:
    """Arquiteto anexa um ARQUIVO (PDF/imagem) à etapa. Espelha revisoes.upload_arquivo.
    `ambiente_id` (projeto_3d) prende o render a um cômodo; `manual_item_id` (manual) a um item."""
    cur = await projeto_writable(session, projeto_id)  # só arquiteto
    _valida_etapa(etapa)
    await _valida_ambiente(session, projeto_id, ambiente_id)
    await _valida_manual_item(session, projeto_id, manual_item_id)
    await _semear(session, projeto_id)

    # idempotência escopada por projeto (id de outro escopo cai no INSERT; vide except abaixo)
    existing = (
        await session.execute(
            text(f"{_ANEXO_SELECT} where id = cast(:a as uuid) and projeto_id = cast(:p as uuid)"),
            {"a": str(anexo_id), "p": str(projeto_id)},
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
    prefix = f"{cur.tenant_id}/projetos/{projeto_id}/etapas/{etapa}/{anexo_id}"
    full_key = f"{prefix}/{'file.pdf' if media['is_pdf'] else 'full.' + media['full_ext']}"
    thumb_key = None if media["is_pdf"] else f"{prefix}/thumb.jpg"
    tamanho = len(media["full_bytes"])
    label_v = (label or "").strip() or None

    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    insert into public.projeto_etapa_anexos
                      (id, projeto_id, tenant_id, etapa, tipo, label, nome_arquivo, content_type,
                       tamanho_bytes, largura, altura, is_pdf, storage_key, thumb_key, criado_por,
                       ambiente_id, manual_item_id)
                    values (cast(:id as uuid), cast(:p as uuid), cast(:t as uuid),
                            cast(:e as public.etapa_projeto), 'arquivo', :label, :nome, :ct, :tam,
                            :larg, :alt, :pdf, :sk, :tk, cast(:uid as uuid), cast(:amb as uuid),
                            cast(:mi as uuid))
                    """
                ),
                {
                    "id": str(anexo_id),
                    "p": str(projeto_id),
                    "t": str(cur.tenant_id),
                    "e": etapa,
                    "label": label_v,
                    "nome": nome,
                    "ct": media["full_content_type"],
                    "tam": tamanho,
                    "larg": media["largura"],
                    "alt": media["altura"],
                    "pdf": media["is_pdf"],
                    "sk": full_key,
                    "tk": thumb_key,
                    "uid": str(user_id),
                    "amb": str(ambiente_id) if ambiente_id else None,
                    "mi": str(manual_item_id) if manual_item_id else None,
                },
            )
    except IntegrityError as e:
        sql = f"{_ANEXO_SELECT} where id = cast(:a as uuid) and projeto_id = cast(:p as uuid)"
        existing = (
            await session.execute(text(sql), {"a": str(anexo_id), "p": str(projeto_id)})
        ).first()
        if existing is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "id de anexo já em uso") from e
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
        action="projeto.etapa_anexo_adicionado",
        entity_type="projeto_etapa_anexo",
        entity_id=anexo_id,
        changed={"etapa": etapa, "tipo": "arquivo", "tamanho_bytes": tamanho},
        entity_label=label_v or nome,
        actor_label=await actor_name(session),
    )
    return dict(
        (
            await session.execute(
                text(f"{_ANEXO_SELECT} where id = cast(:a as uuid)"), {"a": str(anexo_id)}
            )
        ).first()._mapping
    )


async def adicionar_link(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    etapa: str,
    data: EtapaLinkCreate,
    ambiente_id: uuid.UUID | None = None,
    manual_item_id: uuid.UUID | None = None,
) -> dict:
    """Arquiteto anexa um LINK (tour 3D, vídeo, pasta…) à etapa. `ambiente_id` prende ao cômodo;
    `manual_item_id` (manual) prende ao item."""
    cur = await projeto_writable(session, projeto_id)  # só arquiteto
    _valida_etapa(etapa)
    await _valida_ambiente(session, projeto_id, ambiente_id)
    await _valida_manual_item(session, projeto_id, manual_item_id)
    await _semear(session, projeto_id)

    existing = (
        await session.execute(
            text(f"{_ANEXO_SELECT} where id = cast(:a as uuid) and projeto_id = cast(:p as uuid)"),
            {"a": str(data.id), "p": str(projeto_id)},
        )
    ).first()
    if existing is not None:
        return dict(existing._mapping)

    label_v = (data.label or "").strip() or None
    try:
        await session.execute(
            text(
                """
                insert into public.projeto_etapa_anexos
                  (id, projeto_id, tenant_id, etapa, tipo, label, url, criado_por, ambiente_id,
                   manual_item_id)
                values (cast(:id as uuid), cast(:p as uuid), cast(:t as uuid),
                        cast(:e as public.etapa_projeto), 'link', :label, :url, cast(:uid as uuid),
                        cast(:amb as uuid), cast(:mi as uuid))
                """
            ),
            {
                "id": str(data.id),
                "p": str(projeto_id),
                "t": str(cur.tenant_id),
                "e": etapa,
                "label": label_v,
                "url": data.url,
                "uid": str(user_id),
                "amb": str(ambiente_id) if ambiente_id else None,
                "mi": str(manual_item_id) if manual_item_id else None,
            },
        )
    except IntegrityError as e:
        sql = f"{_ANEXO_SELECT} where id = cast(:a as uuid) and projeto_id = cast(:p as uuid)"
        existing = (
            await session.execute(text(sql), {"a": str(data.id), "p": str(projeto_id)})
        ).first()
        if existing is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "id de anexo já em uso") from e
        return dict(existing._mapping)
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e

    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="projeto.etapa_anexo_adicionado",
        entity_type="projeto_etapa_anexo",
        entity_id=data.id,
        changed={"etapa": etapa, "tipo": "link", "url": data.url},
        entity_label=label_v or data.url,
        actor_label=await actor_name(session),
    )
    return dict(
        (
            await session.execute(
                text(f"{_ANEXO_SELECT} where id = cast(:a as uuid)"), {"a": str(data.id)}
            )
        ).first()._mapping
    )


async def serve_etapa_anexo(
    session: AsyncSession, projeto_id: uuid.UUID, anexo_id: uuid.UUID, tipo: str
) -> tuple[bytes, str, str]:
    """Bytes de um anexo de etapa do tipo ARQUIVO (membro do projeto). Espelha serve_arquivo."""
    await projeto_member(session, projeto_id)
    meta = (
        await session.execute(
            text(
                "select tipo, content_type, storage_key, thumb_key, nome_arquivo "
                "from public.projeto_etapa_anexos "
                "where id = cast(:a as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"a": str(anexo_id), "p": str(projeto_id)},
        )
    ).first()
    if meta is None or meta.tipo != "arquivo":
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


async def excluir_etapa_anexo(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, anexo_id: uuid.UUID
) -> dict:
    """Arquiteto remove um anexo da etapa (e os bytes, se for arquivo)."""
    cur = await projeto_writable(session, projeto_id)
    meta = (
        await session.execute(
            text(
                "select pea.tipo, pea.etapa, pea.label, pea.nome_arquivo, pea.storage_key, "
                "pea.ambiente_id, pa.status_3d "
                "from public.projeto_etapa_anexos pea "
                "left join public.projeto_ambientes pa on pa.id = pea.ambiente_id "
                "where pea.id = cast(:a as uuid) and pea.projeto_id = cast(:p as uuid)"
            ),
            {"a": str(anexo_id), "p": str(projeto_id)},
        )
    ).first()
    if meta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "anexo não encontrado")
    # material por cômodo: não remove de um 3D já enviado/aprovado (ver _valida_ambiente)
    _editavel = ("rascunho", "alteracao_pedida")
    if meta.ambiente_id is not None and str(meta.status_3d) not in _editavel:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "cômodo já enviado; recolha-o antes de mexer no material"
        )
    try:
        await session.execute(
            text("delete from public.projeto_etapa_anexos where id = cast(:a as uuid)"),
            {"a": str(anexo_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    if meta.tipo == "arquivo" and meta.storage_key:
        await get_storage().deletar_prefixo(
            f"{cur.tenant_id}/projetos/{projeto_id}/etapas/{meta.etapa}/{anexo_id}"
        )
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="projeto.etapa_anexo_removido",
        entity_type="projeto_etapa_anexo",
        entity_id=anexo_id,
        changed={"etapa": str(meta.etapa), "tipo": meta.tipo},
        entity_label=meta.label or meta.nome_arquivo or str(anexo_id),
        actor_label=await actor_name(session),
    )
    return {"deleted": True}
