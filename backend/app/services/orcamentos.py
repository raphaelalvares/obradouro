"""Serviço do módulo de Orçamento (dentro de Projeto). ARQUITETO-ONLY (projeto_writable em tudo).

Versão = snapshot (R0, R1…); a não-congelada é a editável. "Nova versão" via RPC congela a atual e
clona. Custos por linha em 3 baldes; percentuais globais por versão. Preço calculado aqui (fonte de
verdade) e espelhado no front: Preço = [Σ subtotal×(1+maj)]×(1+BDI)×(1+Imposto).
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.orcamentos import ItemCreate, ItemUpdate, VersaoParams
from app.services import checklist_import
from app.services.audit import log_event
from app.services.common import actor_name, projeto_writable

_VERSAO_COLS = (
    "id, numero, congelado, data, validade, enviado, enviado_em, maj_mo, maj_material, "
    "maj_equipamento, bdi, imposto, observacoes, seq_humano, created_at, updated_at"
)
_ITEM_COLS = (
    "id, etapa, ordem_etapa, descricao, ordem, unidade, quantidade, "
    "valor_mo, valor_material, valor_equipamento"
)
# colunas de parâmetro editáveis (allowlist; nunca vêm do usuário direto)
_PARAM_COLS = (
    "data", "validade", "maj_mo", "maj_material", "maj_equipamento", "bdi", "imposto", "observacoes"
)
_ITEM_PATCH_COLS = (
    "etapa", "descricao", "ordem_etapa", "ordem", "unidade", "quantidade",
    "valor_mo", "valor_material", "valor_equipamento",
)


def _map_42501(e: DBAPIError) -> HTTPException | None:
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


def _f(x) -> float:
    return float(x) if x is not None else 0.0


# ============================ cálculo (fonte de verdade) ============================
def _totais(versao, itens: list[dict]) -> dict:
    base_mo = sum(_f(i["valor_mo"]) for i in itens)
    base_mat = sum(_f(i["valor_material"]) for i in itens)
    base_eq = sum(_f(i["valor_equipamento"]) for i in itens)
    mo = base_mo * (1 + _f(versao["maj_mo"]) / 100)
    mat = base_mat * (1 + _f(versao["maj_material"]) / 100)
    eq = base_eq * (1 + _f(versao["maj_equipamento"]) / 100)
    custo_direto = mo + mat + eq
    bdi_valor = custo_direto * (_f(versao["bdi"]) / 100)
    com_bdi = custo_direto + bdi_valor
    imposto_valor = com_bdi * (_f(versao["imposto"]) / 100)
    preco_final = com_bdi + imposto_valor
    return {
        "base_mo": base_mo, "base_material": base_mat, "base_equipamento": base_eq,
        "mo": mo, "material": mat, "equipamento": eq,
        "custo_direto": custo_direto, "bdi_valor": bdi_valor,
        "imposto_valor": imposto_valor, "preco_final": preco_final,
    }


def _custo_direto_itens(versao, itens: list[dict]) -> float:
    """Custo direto (majorado) de um subconjunto de itens — usado por etapa."""
    mo = sum(_f(i["valor_mo"]) for i in itens) * (1 + _f(versao["maj_mo"]) / 100)
    mat = sum(_f(i["valor_material"]) for i in itens) * (1 + _f(versao["maj_material"]) / 100)
    eq = sum(_f(i["valor_equipamento"]) for i in itens) * (1 + _f(versao["maj_equipamento"]) / 100)
    return mo + mat + eq


def _agrupar_etapas(versao, itens: list[dict]) -> list[dict]:
    # agrupa por NOME da etapa (não por (ordem_etapa, etapa)) — itens da mesma etapa com ordem_etapa
    # divergente (re-import / add manual) caem num grupo só. ordem_etapa do grupo = o menor.
    grupos: dict[str, dict] = {}
    for it in itens:
        g = grupos.get(it["etapa"])
        if g is None:
            grupos[it["etapa"]] = {
                "etapa": it["etapa"], "ordem_etapa": it["ordem_etapa"], "itens": [it]
            }
        else:
            g["ordem_etapa"] = min(g["ordem_etapa"], it["ordem_etapa"])
            g["itens"].append(it)
    out = sorted(grupos.values(), key=lambda g: (g["ordem_etapa"], g["etapa"]))
    for g in out:
        g["custo_direto"] = _custo_direto_itens(versao, g["itens"])
    return out


# ============================ leitura ============================
async def _versao_row(session: AsyncSession, projeto_id: uuid.UUID, versao_id: uuid.UUID):
    row = (
        await session.execute(
            text(
                f"select {_VERSAO_COLS} from public.orcamento_versoes "
                "where id = cast(:v as uuid) and projeto_id = cast(:p as uuid)"
            ),
            {"v": str(versao_id), "p": str(projeto_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "versão de orçamento não encontrada")
    return row


async def _itens_da_versao(session: AsyncSession, versao_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            text(
                f"select {_ITEM_COLS} from public.orcamento_itens "
                "where versao_id = cast(:v as uuid) order by ordem_etapa, ordem, descricao"
            ),
            {"v": str(versao_id)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def get_versao(session: AsyncSession, projeto_id: uuid.UUID, versao_id: uuid.UUID) -> dict:
    await projeto_writable(session, projeto_id)  # arquiteto-only
    row = await _versao_row(session, projeto_id, versao_id)
    versao = dict(row._mapping)
    itens = await _itens_da_versao(session, versao_id)
    versao["totais"] = _totais(versao, itens)
    versao["etapas"] = _agrupar_etapas(versao, itens)
    return versao


async def list_versoes(session: AsyncSession, projeto_id: uuid.UUID) -> list[dict]:
    await projeto_writable(session, projeto_id)  # arquiteto-only
    versoes = (
        await session.execute(
            text(
                f"select {_VERSAO_COLS} from public.orcamento_versoes "
                "where projeto_id = cast(:p as uuid) order by numero"
            ),
            {"p": str(projeto_id)},
        )
    ).all()
    itens = (
        await session.execute(
            text(
                f"select versao_id, {_ITEM_COLS} from public.orcamento_itens "
                "where projeto_id = cast(:p as uuid)"
            ),
            {"p": str(projeto_id)},
        )
    ).all()
    por_versao: dict = {}
    for r in itens:
        d = dict(r._mapping)
        por_versao.setdefault(d.pop("versao_id"), []).append(d)
    out = []
    for v in versoes:
        vd = dict(v._mapping)
        t = _totais(vd, por_versao.get(vd["id"], []))
        out.append({**vd, "custo_direto": t["custo_direto"], "preco_final": t["preco_final"]})
    return out


# ============================ criar versão (R0 / nova) ============================
async def criar_versao(
    session: AsyncSession, user_id: str, projeto_id: uuid.UUID, versao_id: uuid.UUID
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    try:
        row = (
            await session.execute(
                text(
                    """
                    select id, numero, seq_humano
                    from public.criar_orcamento_versao(cast(:id as uuid), cast(:p as uuid))
                    """
                ),
                {"id": str(versao_id), "p": str(projeto_id)},
            )
        ).first()
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    if row is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "não foi possível criar a versão")
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="orcamento.versao_criada",
        entity_type="orcamento_versao",
        entity_id=versao_id,
        changed={"numero": row.numero},
        entity_label=f"Orçamento R{row.numero}",
        entity_seq=row.seq_humano,
        actor_label=await actor_name(session),
    )
    return await get_versao(session, projeto_id, versao_id)


# ============================ parâmetros da versão ============================
async def atualizar_params(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    versao_id: uuid.UUID,
    data: VersaoParams,
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    v = await _versao_row(session, projeto_id, versao_id)
    if v.congelado:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "versão congelada — crie uma nova versão para editar"
        )
    fields = data.model_dump(exclude_unset=True)
    sets, params = [], {"id": str(versao_id)}
    for k in _PARAM_COLS:
        if k in fields:
            sets.append(f"{k} = :{k}")
            params[k] = fields[k]
    if "enviado" in fields:
        sets.append("enviado = :enviado")
        sets.append("enviado_em = case when :enviado then now() else null end")
        params["enviado"] = fields["enviado"]
    if not sets:
        return await get_versao(session, projeto_id, versao_id)
    try:
        await session.execute(
            text(
                f"update public.orcamento_versoes set {', '.join(sets)} "
                "where id = cast(:id as uuid)"
            ),
            params,
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="orcamento.atualizado",
        entity_type="orcamento_versao",
        entity_id=versao_id,
        changed={k: (str(val) if val is not None else None) for k, val in fields.items()},
        entity_label=f"Orçamento R{v.numero}",
        entity_seq=v.seq_humano,
        actor_label=await actor_name(session),
    )
    return await get_versao(session, projeto_id, versao_id)


# ============================ itens ============================
async def add_item(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    versao_id: uuid.UUID,
    data: ItemCreate,
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    v = await _versao_row(session, projeto_id, versao_id)
    if v.congelado:
        raise HTTPException(status.HTTP_409_CONFLICT, "versão congelada")
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    insert into public.orcamento_itens
                      (id, versao_id, projeto_id, tenant_id, etapa, ordem_etapa, descricao, ordem,
                       unidade, quantidade, valor_mo, valor_material, valor_equipamento)
                    values (cast(:id as uuid), cast(:v as uuid), cast(:p as uuid), cast(:t as uuid),
                            :etapa, :ordem_etapa, :descricao, :ordem, :unidade, :quantidade,
                            :valor_mo, :valor_material, :valor_equipamento)
                    """
                ),
                {
                    "id": str(data.id), "v": str(versao_id), "p": str(projeto_id),
                    "t": str(cur.tenant_id), "etapa": data.etapa, "ordem_etapa": data.ordem_etapa,
                    "descricao": data.descricao, "ordem": data.ordem, "unidade": data.unidade,
                    "quantidade": data.quantidade, "valor_mo": data.valor_mo,
                    "valor_material": data.valor_material,
                    "valor_equipamento": data.valor_equipamento,
                },
            )
    except IntegrityError:
        pass  # mesmo id reenviado (offline/retry) → idempotente
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    return await get_versao(session, projeto_id, versao_id)


async def edit_item(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    versao_id: uuid.UUID,
    item_id: uuid.UUID,
    data: ItemUpdate,
) -> dict:
    await projeto_writable(session, projeto_id)
    v = await _versao_row(session, projeto_id, versao_id)
    if v.congelado:
        raise HTTPException(status.HTTP_409_CONFLICT, "versão congelada")
    fields = {
        k: val for k, val in data.model_dump(exclude_unset=True).items() if k in _ITEM_PATCH_COLS
    }
    if not fields:
        return await get_versao(session, projeto_id, versao_id)
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    params = dict(fields)
    params["i"] = str(item_id)
    params["v"] = str(versao_id)
    try:
        res = (
            await session.execute(
                text(
                    f"update public.orcamento_itens set {sets} "
                    "where id = cast(:i as uuid) and versao_id = cast(:v as uuid) returning id"
                ),
                params,
            )
        ).first()
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item não encontrado")
    return await get_versao(session, projeto_id, versao_id)


async def delete_item(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    versao_id: uuid.UUID,
    item_id: uuid.UUID,
) -> dict:
    await projeto_writable(session, projeto_id)
    v = await _versao_row(session, projeto_id, versao_id)
    if v.congelado:
        raise HTTPException(status.HTTP_409_CONFLICT, "versão congelada")
    try:
        await session.execute(
            text(
                "delete from public.orcamento_itens "
                "where id = cast(:i as uuid) and versao_id = cast(:v as uuid)"
            ),
            {"i": str(item_id), "v": str(versao_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    return await get_versao(session, projeto_id, versao_id)


# ============================ import (Excel — atalho opcional) ============================
async def importar(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    versao_id: uuid.UUID,
    arquivo,
) -> dict:
    cur = await projeto_writable(session, projeto_id)
    v = await _versao_row(session, projeto_id, versao_id)
    if v.congelado:
        raise HTTPException(status.HTTP_409_CONFLICT, "versão congelada")
    raw = await arquivo.read()
    payload = checklist_import.parse_xlsx(raw)  # valida formato/tamanho → 413/422

    # itens existentes: dedupe por etapa+descrição normalizados (re-import não duplica) + REUSO do
    # ordem_etapa/ordem da etapa que já existe (evita dividir a mesma etapa em dois grupos).
    existentes = await _itens_da_versao(session, versao_id)
    vistos = {
        (checklist_import.norm_nome(i["etapa"]), checklist_import.norm_nome(i["descricao"]))
        for i in existentes
    }
    oe_por_etapa: dict[str, int] = {}
    max_ordem_por_etapa: dict[str, int] = {}
    for i in existentes:
        en = checklist_import.norm_nome(i["etapa"])
        oe_por_etapa.setdefault(en, i["ordem_etapa"])
        max_ordem_por_etapa[en] = max(max_ordem_por_etapa.get(en, 0), i["ordem"] or 0)
    max_oe = max((i["ordem_etapa"] for i in existentes), default=0)

    novos = 0
    for et in payload:
        et_nome = et["nome"]
        et_norm = checklist_import.norm_nome(et_nome)
        if et_norm in oe_por_etapa:
            oe = oe_por_etapa[et_norm]
        else:
            max_oe += 1
            oe = max_oe
            oe_por_etapa[et_norm] = oe
        ordem = max_ordem_por_etapa.get(et_norm, 0)
        for it in et.get("itens", []):
            chave = (et_norm, checklist_import.norm_nome(it["nome"]))
            if chave in vistos:
                continue
            vistos.add(chave)
            ordem += 1
            max_ordem_por_etapa[et_norm] = ordem
            try:
                async with session.begin_nested():
                    await session.execute(
                        text(
                            """
                            insert into public.orcamento_itens
                              (id, versao_id, projeto_id, tenant_id, etapa, ordem_etapa, descricao,
                               ordem, unidade, quantidade, valor_mo, valor_material,
                               valor_equipamento)
                            values (gen_random_uuid(), cast(:v as uuid), cast(:p as uuid),
                                    cast(:t as uuid), :etapa, :oe, :descricao, :ordem, :unidade,
                                    :quantidade, :vmo, :vmat, :veq)
                            """
                        ),
                        {
                            "v": str(versao_id), "p": str(projeto_id), "t": str(cur.tenant_id),
                            "etapa": et_nome, "oe": oe, "descricao": it["nome"], "ordem": ordem,
                            "unidade": it.get("unidade"), "quantidade": it.get("quantidade"),
                            "vmo": it.get("custo_mao_obra") or 0,
                            "vmat": it.get("custo_material") or 0,
                            "veq": it.get("custo_equipamento") or 0,
                        },
                    )
                novos += 1
            except DBAPIError as e:
                raise (_map_42501(e) or e) from e

    await log_event(
        session,
        tenant=cur.tenant_id,
        actor_id=user_id,
        obra_id=None,
        projeto_id=projeto_id,
        action="orcamento.importado",
        entity_type="orcamento_versao",
        entity_id=versao_id,
        changed={"itens_novos": novos},
        entity_label=f"Orçamento R{v.numero}",
        entity_seq=v.seq_humano,
        actor_label=await actor_name(session),
    )
    return await get_versao(session, projeto_id, versao_id)
