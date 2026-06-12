"""Serviço do módulo de Orçamento (dentro de Projeto). ARQUITETO-ONLY (projeto_writable em tudo).

Versão = snapshot (R0, R1…); a não-congelada é a editável. "Nova versão" via RPC congela a atual e
clona. Custo por linha = UNITÁRIO em 3 baldes (M.O/material/equipamento); subtotal da linha =
valor × quantidade (0068). Percentuais globais por versão. Preço calculado aqui (fonte de verdade) e
espelhado no front: Preço = [Σ (unit×qtd)×(1+maj)]×(1+BDI)×(1+Imposto).
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.orcamentos import ItemCreate, ItemUpdate, VersaoParams
from app.services import checklist_import
from app.services.audit import log_event
from app.services.catalogo import _custo_unit
from app.services.common import actor_name, projeto_member, projeto_writable

_VERSAO_COLS = (
    "id, numero, congelado, data, validade, enviado, enviado_em, maj_mo, maj_material, "
    "maj_equipamento, bdi, imposto, observacoes, seq_humano, created_at, updated_at"
)
_ITEM_COLS = (
    "id, etapa, ordem_etapa, descricao, ordem, ambiente, unidade, quantidade, "
    "valor_mo, valor_material, valor_equipamento"
)
# colunas de parâmetro editáveis (allowlist; nunca vêm do usuário direto)
_PARAM_COLS = (
    "data", "validade", "maj_mo", "maj_material", "maj_equipamento", "bdi", "imposto", "observacoes"
)
_ITEM_PATCH_COLS = (
    "etapa", "descricao", "ordem_etapa", "ordem", "ambiente", "unidade", "quantidade",
    "valor_mo", "valor_material", "valor_equipamento",
)


def _map_42501(e: DBAPIError) -> HTTPException | None:
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


def _f(x) -> float:
    return float(x) if x is not None else 0.0


def _mult(item: dict) -> float:
    """Multiplicador da linha = quantidade (quando > 0); qtd null/0/negativa = verba → 1. Mesma
    regra da 0068 e da central (case when qtd>0 then qtd else 1), p/ os totais baterem."""
    q = item.get("quantidade")
    return float(q) if (q is not None and q > 0) else 1.0


def _unit_do_import(it: dict) -> dict:
    """Linha da planilha → (quantidade + UNITÁRIOS). As colunas M.O/MAT/EQUIP da planilha são
    SUBTOTAL de linha POR BALDE (TOTAL = soma delas); o unitário = subtotal / quantidade. qtd
    null/0/negativa = verba → ÷1 (espelha _custo_unit/_mult). PURA (testável)."""
    q = it.get("quantidade")
    if q is not None and q < 0:  # qtd negativa (digitação no .xlsx) → trata como verba
        q = None
    return {
        "quantidade": q,
        "valor_mo": _custo_unit(it.get("custo_mao_obra"), q),
        "valor_material": _custo_unit(it.get("custo_material"), q),
        "valor_equipamento": _custo_unit(it.get("custo_equipamento"), q),
    }


# ============================ cálculo (fonte de verdade) ============================
def _aplicar_percentuais(base_mo, base_mat, base_eq, maj_mo, maj_mat, maj_eq, bdi, imposto) -> dict:
    """Aplica majoração por tipo + BDI + imposto sobre as BASES (cruas) → valores derivados.
    Fonte ÚNICA da fórmula de preço:
        Preço = [Σ base_tipo × (1 + maj_tipo/100)] × (1 + BDI/100) × (1 + Imposto/100).
    Usada pelo total da versão (_totais, bases somadas em Python) e pela central (bases somadas no
    SQL). Recebe percentuais como número (10 = 10%)."""
    mo = base_mo * (1 + maj_mo / 100)
    mat = base_mat * (1 + maj_mat / 100)
    eq = base_eq * (1 + maj_eq / 100)
    custo_direto = mo + mat + eq
    bdi_valor = custo_direto * (bdi / 100)
    com_bdi = custo_direto + bdi_valor
    imposto_valor = com_bdi * (imposto / 100)
    return {
        "mo": mo, "material": mat, "equipamento": eq,
        "custo_direto": custo_direto, "bdi_valor": bdi_valor,
        "imposto_valor": imposto_valor, "preco_final": com_bdi + imposto_valor,
    }


def _totais(versao, itens: list[dict]) -> dict:
    # base por tipo = Σ (unitário × quantidade) — subtotal de linha somado em precisão cheia.
    base_mo = sum(_f(i["valor_mo"]) * _mult(i) for i in itens)
    base_mat = sum(_f(i["valor_material"]) * _mult(i) for i in itens)
    base_eq = sum(_f(i["valor_equipamento"]) * _mult(i) for i in itens)
    r = _aplicar_percentuais(
        base_mo, base_mat, base_eq,
        _f(versao["maj_mo"]), _f(versao["maj_material"]), _f(versao["maj_equipamento"]),
        _f(versao["bdi"]), _f(versao["imposto"]),
    )
    return {"base_mo": base_mo, "base_material": base_mat, "base_equipamento": base_eq, **r}


def _custo_direto_itens(versao, itens: list[dict]) -> float:
    """Custo direto (majorado) de um subconjunto de itens — usado por etapa/cômodo. Base por tipo =
    Σ (unitário × quantidade)."""
    def base(campo: str) -> float:
        return sum(_f(i[campo]) * _mult(i) for i in itens)

    mo = base("valor_mo") * (1 + _f(versao["maj_mo"]) / 100)
    mat = base("valor_material") * (1 + _f(versao["maj_material"]) / 100)
    eq = base("valor_equipamento") * (1 + _f(versao["maj_equipamento"]) / 100)
    return mo + mat + eq


# tetos das colunas do item (numeric(14,3) qtd; numeric(18,4) unitários) — barram overflow 22003→500
_QTD_MAX = 99_999_999_999.999
_VALOR_MAX = 99_999_999_999_999.9999


def _linha_do_template(
    custo_mo, custo_material, custo_equipamento, por_area: bool, fator, area
) -> dict:
    """Quantidade + UNITÁRIOS (R$) de uma linha gerada por um item de template aplicado a uma área.
    qtd = por_area ? round(fator×área, 3) : fator. valor_* = custo unitário do catálogo (round 4
    casas = escala do orcamento_itens); o subtotal (unit×qtd) é calculado depois. Fonte única da
    matemática do 'aplicar' (espelhada no preview do front)."""
    qtd = round(_f(fator) * _f(area), 3) if por_area else _f(fator)
    return {
        "quantidade": qtd,
        "valor_mo": round(_f(custo_mo), 4),
        "valor_material": round(_f(custo_material), 4),
        "valor_equipamento": round(_f(custo_equipamento), 4),
    }


def _linha_excede_teto(linha: dict) -> bool:
    """A linha gerada (qtd/unitários) cabe nas colunas numeric? fator×área (qtd) ou unitário absurdo
    estouraria o numeric (22003 → 500); preferimos 422 limpo."""
    return (
        linha["quantidade"] > _QTD_MAX
        or linha["valor_mo"] > _VALOR_MAX
        or linha["valor_material"] > _VALOR_MAX
        or linha["valor_equipamento"] > _VALOR_MAX
    )


def _agrupar_ambientes(versao, itens: list[dict]) -> list[dict]:
    # pivot por cômodo: agrupa por NOME do ambiente (None = "Geral"). Mantém a ordem original dos
    # itens dentro do grupo. Grupos ordenados por nome; o "Geral" (sem cômodo) vai por último.
    grupos: dict = {}
    for it in itens:
        amb = it.get("ambiente")
        grupos.setdefault(amb, {"ambiente": amb, "itens": []})["itens"].append(it)
    out = sorted(
        grupos.values(), key=lambda g: (g["ambiente"] is None, (g["ambiente"] or "").lower())
    )
    for g in out:
        g["custo_direto"] = _custo_direto_itens(versao, g["itens"])
    return out


def _venda_fator(versao) -> float:
    """Fator global de venda = (1+BDI/100) × (1+imposto/100), aplicado sobre o custo majorado."""
    return (1 + _f(versao["bdi"]) / 100) * (1 + _f(versao["imposto"]) / 100)


def _venda_item(versao, item: dict) -> float:
    """PREÇO DE VENDA da linha = custo direto majorado × (1+BDI) × (1+imposto). SPEC (referência
    testável) da fórmula que as funções SECURITY DEFINER do 0078 implementam em SQL — a proposta do
    cliente é servida por elas (orcamentos.list_propostas/get_proposta). Como o preço é linear nos
    itens, Σ _venda_item == totais.preco_final (provado em test_venda_soma_*)."""
    mo = _f(item["valor_mo"]) * (1 + _f(versao["maj_mo"]) / 100)
    mat = _f(item["valor_material"]) * (1 + _f(versao["maj_material"]) / 100)
    eq = _f(item["valor_equipamento"]) * (1 + _f(versao["maj_equipamento"]) / 100)
    return (mo + mat + eq) * _mult(item) * _venda_fator(versao)


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
    versao["ambientes"] = _agrupar_ambientes(versao, itens)
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


# ============================ proposta (portal do cliente) ============================
# Lido por QUALQUER membro do projeto (cliente incluso) via funções SECURITY DEFINER (0078) que
# devolvem SÓ a visão de VENDA — as tabelas-base seguem arquiteto-only (RLS é por linha e entregaria
# custo cru/maj/BDI; ver 0078). A fórmula vive em SQL lá (espelha _totais/_venda_item daqui).
async def list_propostas(session: AsyncSession, projeto_id: uuid.UUID) -> list[dict]:
    """Versões ENVIADAS na visão de proposta (resumo). 404 do projeto se não-membro."""
    await projeto_member(session, projeto_id)
    rows = (
        await session.execute(
            text(
                "select id, numero, data, validade, enviado_em, preco_final "
                "from public.orcamento_proposta_resumos(cast(:p as uuid))"
            ),
            {"p": str(projeto_id)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


def _proposta_agrupar(rows: list[dict]) -> list[dict]:
    """Agrupa as linhas de venda (já calculadas no SQL) por etapa — só apresentação, sem fórmula.
    Ordem da etapa = menor ordem_etapa (espelha _agrupar_etapas)."""
    grupos: dict[str, dict] = {}
    for r in rows:
        g = grupos.get(r["etapa"])
        if g is None:
            grupos[r["etapa"]] = {
                "etapa": r["etapa"], "_oe": r["ordem_etapa"], "valor": 0.0, "itens": []
            }
            g = grupos[r["etapa"]]
        else:
            g["_oe"] = min(g["_oe"], r["ordem_etapa"])
        valor = float(r["valor"]) if r["valor"] is not None else 0.0
        g["valor"] += valor
        g["itens"].append(
            {
                "descricao": r["descricao"], "ambiente": r["ambiente"], "unidade": r["unidade"],
                "quantidade": float(r["quantidade"]) if r["quantidade"] is not None else None,
                "valor": valor,
            }
        )
    out = sorted(grupos.values(), key=lambda g: (g["_oe"], g["etapa"]))
    for g in out:
        g.pop("_oe")
    return out


async def get_proposta(session: AsyncSession, projeto_id: uuid.UUID, versao_id: uuid.UUID) -> dict:
    """Proposta completa (etapas + preços de VENDA por linha) — visão "o que o cliente vê". O
    arquiteto acessa qualquer versão (preview/gerar PDF p/ enviar); o cliente só as ENVIADAS (regra
    nas funções definer 0078). 404 se a versão não existe / não é visível a quem pede."""
    cur = await projeto_member(session, projeto_id)
    head = (
        await session.execute(
            text(
                "select id, numero, data, validade, enviado_em, observacoes, preco_final "
                "from public.orcamento_proposta_versao(cast(:p as uuid), cast(:v as uuid))"
            ),
            {"p": str(projeto_id), "v": str(versao_id)},
        )
    ).first()
    if head is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proposta não encontrada")
    rows = (
        await session.execute(
            text(
                "select etapa, ordem_etapa, descricao, ordem, ambiente, unidade, quantidade, valor "
                "from public.orcamento_proposta_itens(cast(:p as uuid), cast(:v as uuid))"
            ),
            {"p": str(projeto_id), "v": str(versao_id)},
        )
    ).all()
    h = dict(head._mapping)
    etapas = _proposta_agrupar([dict(r._mapping) for r in rows])
    return {**h, "projeto_nome": cur.nome, "etapas": etapas}


# ============================ central (cross-projeto) ============================
async def central(session: AsyncSession) -> list[dict]:
    """Central de orçamentos: 1 linha por PROJETO do arquiteto, com a versão EDITÁVEL (a "atual",
    congelado=false) + o total. Cross-projeto: escopo via RLS + `is_arquiteto_ativo_projeto` (sem o
    projeto_writable, que é por-projeto). Projeto sem orçamento entra com tem_orcamento=false (CTA
    "criar" no front). Bases somadas em SQL; o preço usa a fórmula única (_aplicar_percentuais) →
    bate com o total dentro do projeto. Sem auth manual: /me exige sessão e a RLS filtra."""
    rows = (
        await session.execute(
            text(
                """
                select p.id as projeto_id, p.nome as projeto_nome, p.seq_humano as projeto_seq,
                       v.id as versao_id, v.numero, v.seq_humano as versao_seq, v.enviado,
                       v.data, v.validade, v.updated_at as atualizado_em,
                       v.maj_mo, v.maj_material, v.maj_equipamento, v.bdi, v.imposto,
                       coalesce(b.base_mo, 0)         as base_mo,
                       coalesce(b.base_material, 0)   as base_material,
                       coalesce(b.base_equipamento, 0) as base_equipamento,
                       coalesce(c.n, 0)               as n_versoes
                from public.projetos p
                left join public.orcamento_versoes v
                  on v.projeto_id = p.id and v.congelado = false
                left join lateral (
                  -- base por tipo = Σ (unitário × quantidade); qtd null/0 = verba → ×1 (= _mult).
                  select sum(i.valor_mo * i.m)          as base_mo,
                         sum(i.valor_material * i.m)    as base_material,
                         sum(i.valor_equipamento * i.m) as base_equipamento
                  from (
                    select valor_mo, valor_material, valor_equipamento,
                           case when quantidade > 0 then quantidade else 1 end as m
                    from public.orcamento_itens where versao_id = v.id
                  ) i
                ) b on true
                left join lateral (
                  select count(*) as n from public.orcamento_versoes vv where vv.projeto_id = p.id
                ) c on true
                where public.is_arquiteto_ativo_projeto(p.id)
                order by (v.id is null), v.updated_at desc nulls last, p.nome, p.seq_humano
                """
            )
        )
    ).all()
    out = []
    for r in rows:
        d = dict(r._mapping)
        tem = d["versao_id"] is not None
        calc = (
            _aplicar_percentuais(
                _f(d["base_mo"]), _f(d["base_material"]), _f(d["base_equipamento"]),
                _f(d["maj_mo"]), _f(d["maj_material"]), _f(d["maj_equipamento"]),
                _f(d["bdi"]), _f(d["imposto"]),
            )
            if tem
            else None
        )
        out.append(
            {
                "projeto_id": d["projeto_id"],
                "projeto_nome": d["projeto_nome"],
                "projeto_seq": d["projeto_seq"],
                "tem_orcamento": tem,
                "versao_id": d["versao_id"],
                "numero": d["numero"],
                "versao_seq": d["versao_seq"],
                "enviado": bool(d["enviado"]),
                "data": d["data"],
                "validade": d["validade"],
                "atualizado_em": d["atualizado_em"],
                "n_versoes": d["n_versoes"],
                "custo_direto": calc["custo_direto"] if calc else 0.0,
                "preco_final": calc["preco_final"] if calc else 0.0,
            }
        )
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
                       ambiente, unidade, quantidade, valor_mo, valor_material, valor_equipamento)
                    values (cast(:id as uuid), cast(:v as uuid), cast(:p as uuid), cast(:t as uuid),
                            :etapa, :ordem_etapa, :descricao, :ordem, :ambiente, :unidade,
                            :quantidade, :valor_mo, :valor_material, :valor_equipamento)
                    """
                ),
                {
                    "id": str(data.id), "v": str(versao_id), "p": str(projeto_id),
                    "t": str(cur.tenant_id), "etapa": data.etapa, "ordem_etapa": data.ordem_etapa,
                    "descricao": data.descricao, "ordem": data.ordem,
                    "ambiente": (data.ambiente or None), "unidade": data.unidade,
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
            # planilha traz SUBTOTAL por balde → grava UNITÁRIO (subtotal / qtd); senão a leitura
            # (que multiplica por qtd) inflaria o orçamento. _unit_do_import espelha _custo_unit.
            lin = _unit_do_import(it)
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
                            "unidade": it.get("unidade"), "quantidade": lin["quantidade"],
                            "vmo": lin["valor_mo"],
                            "vmat": lin["valor_material"],
                            "veq": lin["valor_equipamento"],
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


# ============================ aplicar template do livro (Fatia 2) ============================
async def aplicar_template(
    session: AsyncSession,
    user_id: str,
    projeto_id: uuid.UUID,
    versao_id: uuid.UUID,
    template_id: uuid.UUID,
    ambiente_nome: str,
    area_m2: float | None,
) -> dict:
    """Gera as linhas de um cômodo a partir de um template do livro. qtd e subtotais via
    _linha_do_template (custo_unit do catálogo × qtd). Dedupe por (cômodo, etapa, descrição) — não
    duplica ao re-aplicar. Reusa ordem_etapa/ordem das etapas já existentes (não racha grupos)."""
    cur = await projeto_writable(session, projeto_id)
    v = await _versao_row(session, projeto_id, versao_id)
    if v.congelado:
        raise HTTPException(status.HTTP_409_CONFLICT, "versão congelada")

    # template + serviços do catálogo (RLS self → tem de ser do tenant do arquiteto)
    itens_tpl = (
        await session.execute(
            text(
                """
                select ti.servico_id, ti.etapa, ti.por_area, ti.fator, ti.ordem,
                       s.descricao, s.unidade, s.custo_mo, s.custo_material, s.custo_equipamento,
                       s.etapa_sugerida
                from public.ambiente_template_itens ti
                join public.ambiente_templates t on t.id = ti.template_id
                join public.servicos_catalogo s on s.id = ti.servico_id
                where ti.template_id = cast(:t as uuid) and t.tenant_id = cast(:tenant as uuid)
                order by ti.ordem, s.descricao
                """
            ),
            {"t": str(template_id), "tenant": str(cur.tenant_id)},
        )
    ).all()
    if not itens_tpl:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template não encontrado ou sem itens")
    if any(r.por_area for r in itens_tpl) and (area_m2 is None or area_m2 <= 0):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "informe a área do cômodo (há itens por m²)"
        )

    existentes = await _itens_da_versao(session, versao_id)
    amb_norm = checklist_import.norm_nome(ambiente_nome)
    vistos = {
        (
            checklist_import.norm_nome(i.get("ambiente") or ""),
            checklist_import.norm_nome(i["etapa"]),
            checklist_import.norm_nome(i["descricao"]),
        )
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
    for r in itens_tpl:
        etapa = (r.etapa or r.etapa_sugerida or "Serviços").strip() or "Serviços"
        en = checklist_import.norm_nome(etapa)
        if en in oe_por_etapa:
            oe = oe_por_etapa[en]
        else:
            max_oe += 1
            oe = max_oe
            oe_por_etapa[en] = oe
        chave = (amb_norm, en, checklist_import.norm_nome(r.descricao))
        if chave in vistos:
            continue
        vistos.add(chave)
        ordem = max_ordem_por_etapa.get(en, 0) + 1
        max_ordem_por_etapa[en] = ordem
        linha = _linha_do_template(
            r.custo_mo, r.custo_material, r.custo_equipamento, r.por_area, r.fator, area_m2
        )
        if _linha_excede_teto(linha):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "quantidade ou valor acima do limite — revise a área ou o fator do template",
            )
        try:
            async with session.begin_nested():
                await session.execute(
                    text(
                        """
                        insert into public.orcamento_itens
                          (id, versao_id, projeto_id, tenant_id, etapa, ordem_etapa, descricao,
                           ordem, ambiente, unidade, quantidade, valor_mo, valor_material,
                           valor_equipamento)
                        values (gen_random_uuid(), cast(:v as uuid), cast(:p as uuid),
                                cast(:t as uuid), :etapa, :oe, :descricao, :ordem, :amb, :unidade,
                                :qtd, :vmo, :vmat, :veq)
                        """
                    ),
                    {
                        "v": str(versao_id), "p": str(projeto_id), "t": str(cur.tenant_id),
                        "etapa": etapa, "oe": oe, "descricao": r.descricao, "ordem": ordem,
                        "amb": ambiente_nome, "unidade": r.unidade, "qtd": linha["quantidade"],
                        "vmo": linha["valor_mo"], "vmat": linha["valor_material"],
                        "veq": linha["valor_equipamento"],
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
        action="orcamento.template_aplicado",
        entity_type="orcamento_versao",
        entity_id=versao_id,
        changed={"ambiente": ambiente_nome, "itens_novos": novos},
        entity_label=f"Orçamento R{v.numero}",
        entity_seq=v.seq_humano,
        actor_label=await actor_name(session),
    )
    return await get_versao(session, projeto_id, versao_id)
