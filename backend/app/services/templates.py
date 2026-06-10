"""Serviço dos Templates de ambiente (Livro de referências · Fatia 2). ARQUITETO-ONLY via RLS self
(tenant_id = auth.uid()). Template = receita por tipo×nível com serviços do catálogo (0063) e regra
de quantidade (fixa ou por m²). 'Aplicar' vive em services/orcamentos.py (escreve orcamento_itens);
aqui ficam CRUD + 'promover' (salvar linhas reais como template)."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.catalogo import PromoverServicoIn
from app.schemas.templates import (
    _FATOR_MAX,
    PromoverTemplateIn,
    TemplateCreate,
    TemplateItemCreate,
    TemplateItemUpdate,
    TemplateUpdate,
)
from app.services import catalogo as cat_svc
from app.services.checklist_import import norm_nome

_TPL_COLS = "id, tipo, nivel, area_referencia, ativo, created_at, updated_at"
_TPL_PATCH_COLS = ("tipo", "nivel", "area_referencia", "ativo")
_ITEM_PATCH_COLS = ("etapa", "por_area", "fator", "ordem")
_DUP_TPL = "já existe um template com esse tipo e nível"


def _map_42501(e: DBAPIError) -> HTTPException | None:
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


# ============================ leitura ============================
async def listar(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            text(
                f"""
                select {_TPL_COLS},
                       (select count(*) from public.ambiente_template_itens ti
                        where ti.template_id = t.id) as n_itens
                from public.ambiente_templates t
                where t.tenant_id = (select auth.uid())
                order by t.tipo, t.nivel
                """
            )
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def _itens(session: AsyncSession, template_id: uuid.UUID) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                select ti.id, ti.servico_id, s.descricao, s.unidade,
                       s.custo_mo, s.custo_material, s.custo_equipamento,
                       ti.etapa, ti.por_area, ti.fator, ti.ordem
                from public.ambiente_template_itens ti
                join public.servicos_catalogo s on s.id = ti.servico_id
                where ti.template_id = cast(:t as uuid) and ti.tenant_id = (select auth.uid())
                order by ti.ordem, s.descricao
                """
            ),
            {"t": str(template_id)},
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def _row(session: AsyncSession, template_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(
                f"select {_TPL_COLS} from public.ambiente_templates "
                "where id = cast(:t as uuid) and tenant_id = (select auth.uid())"
            ),
            {"t": str(template_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template não encontrado")
    return dict(row._mapping)


async def get(session: AsyncSession, template_id: uuid.UUID) -> dict:
    tpl = await _row(session, template_id)
    tpl["itens"] = await _itens(session, template_id)
    return tpl


# ============================ template (cabeçalho) ============================
async def criar(session: AsyncSession, user_id: str, data: TemplateCreate) -> dict:
    nt, nn = norm_nome(data.tipo), norm_nome(data.nivel)
    if not nt or not nn:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "tipo/nível inválidos")
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    insert into public.ambiente_templates
                      (id, tenant_id, tipo, nivel, tipo_norm, nivel_norm, area_referencia,
                       created_by)
                    values (cast(:id as uuid), (select auth.uid()), :tipo, :nivel, :nt, :nn,
                            :area, (select auth.uid()))
                    """
                ),
                {
                    "id": str(data.id), "tipo": data.tipo, "nivel": data.nivel,
                    "nt": nt, "nn": nn, "area": data.area_referencia,
                },
            )
    except IntegrityError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, _DUP_TPL) from e
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    return await get(session, data.id)


async def atualizar(
    session: AsyncSession, user_id: str, template_id: uuid.UUID, data: TemplateUpdate
) -> dict:
    await _row(session, template_id)
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if k in _TPL_PATCH_COLS}
    if not fields:
        return await get(session, template_id)
    sets = [f"{k} = :{k}" for k in fields]
    params = dict(fields)
    if "tipo" in fields:
        params["nt"] = norm_nome(fields["tipo"])
        sets.append("tipo_norm = :nt")
    if "nivel" in fields:
        params["nn"] = norm_nome(fields["nivel"])
        sets.append("nivel_norm = :nn")
    params["t"] = str(template_id)
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    f"update public.ambiente_templates set {', '.join(sets)} "
                    "where id = cast(:t as uuid) and tenant_id = (select auth.uid())"
                ),
                params,
            )
    except IntegrityError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, _DUP_TPL) from e
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    return await get(session, template_id)


async def excluir(session: AsyncSession, user_id: str, template_id: uuid.UUID) -> None:
    await _row(session, template_id)
    await session.execute(
        text(
            "delete from public.ambiente_templates "
            "where id = cast(:t as uuid) and tenant_id = (select auth.uid())"
        ),
        {"t": str(template_id)},
    )


# ============================ itens do template ============================
async def add_item(
    session: AsyncSession, user_id: str, template_id: uuid.UUID, data: TemplateItemCreate
) -> dict:
    await _row(session, template_id)  # 404 se o template não é do tenant
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    insert into public.ambiente_template_itens
                      (id, template_id, tenant_id, servico_id, etapa, por_area, fator, ordem)
                    values (cast(:id as uuid), cast(:t as uuid), (select auth.uid()),
                            cast(:s as uuid), :etapa, :por_area, :fator, :ordem)
                    """
                ),
                {
                    "id": str(data.id), "t": str(template_id), "s": str(data.servico_id),
                    "etapa": data.etapa, "por_area": data.por_area, "fator": data.fator,
                    "ordem": data.ordem,
                },
            )
    except IntegrityError:
        pass  # mesmo id reenviado → idempotente
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    return await get(session, template_id)


async def edit_item(
    session: AsyncSession,
    user_id: str,
    template_id: uuid.UUID,
    item_id: uuid.UUID,
    data: TemplateItemUpdate,
) -> dict:
    await _row(session, template_id)
    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if k in _ITEM_PATCH_COLS}
    if not fields:
        return await get(session, template_id)
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    params = dict(fields)
    params["i"] = str(item_id)
    params["t"] = str(template_id)
    try:
        res = (
            await session.execute(
                text(
                    f"update public.ambiente_template_itens set {sets} "
                    "where id = cast(:i as uuid) and template_id = cast(:t as uuid) "
                    "and tenant_id = (select auth.uid()) returning id"
                ),
                params,
            )
        ).first()
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    if res is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "item do template não encontrado")
    return await get(session, template_id)


async def delete_item(
    session: AsyncSession, user_id: str, template_id: uuid.UUID, item_id: uuid.UUID
) -> dict:
    await _row(session, template_id)
    await session.execute(
        text(
            "delete from public.ambiente_template_itens "
            "where id = cast(:i as uuid) and template_id = cast(:t as uuid) "
            "and tenant_id = (select auth.uid())"
        ),
        {"i": str(item_id), "t": str(template_id)},
    )
    return await get(session, template_id)


# ============================ promover (orçamento real → template) ============================
async def promover(session: AsyncSession, user_id: str, data: PromoverTemplateIn) -> dict:
    """Salva linhas reais como template. Cada linha → serviço no catálogo (merge por nome) + item do
    template como QUANTIDADE FIXA (o arquiteto marca depois quais escalam por m²). 409 se já existir
    template com o mesmo tipo×nível."""
    nt, nn = norm_nome(data.tipo), norm_nome(data.nivel)
    if not nt or not nn:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "tipo/nível inválidos")
    ja = (
        await session.execute(
            text(
                "select 1 from public.ambiente_templates "
                "where tenant_id = (select auth.uid()) and tipo_norm = :nt and nivel_norm = :nn"
            ),
            {"nt": nt, "nn": nn},
        )
    ).first()
    if ja is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, _DUP_TPL)

    # valida os fatores ANTES de qualquer escrita (input barato falha cedo, sem mexer no catálogo).
    # NÃO limitar quantidade no schema: é o DIVISOR do unitário no catálogo (qtd grande é legítima).
    fatores = [
        (linha.quantidade if (linha.quantidade and linha.quantidade > 0) else 1.0)
        for linha in data.itens
    ]
    if any(f > _FATOR_MAX for f in fatores):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "quantidade de uma linha acima do limite"
        )

    novo_id = uuid.uuid4()
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    insert into public.ambiente_templates
                      (id, tenant_id, tipo, nivel, tipo_norm, nivel_norm, area_referencia,
                       created_by)
                    values (cast(:id as uuid), (select auth.uid()), :tipo, :nivel, :nt, :nn,
                            :area, (select auth.uid()))
                    """
                ),
                {
                    "id": str(novo_id), "tipo": data.tipo, "nivel": data.nivel,
                    "nt": nt, "nn": nn, "area": data.area_referencia,
                },
            )
    except IntegrityError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, _DUP_TPL) from e
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e

    for idx, linha in enumerate(data.itens):
        serv = await cat_svc.promover(
            session,
            user_id,
            PromoverServicoIn(
                descricao=linha.descricao,
                unidade=linha.unidade,
                quantidade=linha.quantidade,
                valor_mo=linha.valor_mo,
                valor_material=linha.valor_material,
                valor_equipamento=linha.valor_equipamento,
                etapa_sugerida=linha.etapa,
            ),
        )
        fator = fatores[idx]  # já validado <= _FATOR_MAX acima
        try:
            async with session.begin_nested():
                await session.execute(
                    text(
                        """
                        insert into public.ambiente_template_itens
                          (id, template_id, tenant_id, servico_id, etapa, por_area, fator, ordem)
                        values (gen_random_uuid(), cast(:t as uuid), (select auth.uid()),
                                cast(:s as uuid), :etapa, false, :fator, :ordem)
                        """
                    ),
                    {
                        "t": str(novo_id), "s": str(serv["id"]), "etapa": linha.etapa,
                        "fator": fator, "ordem": idx,
                    },
                )
        except DBAPIError as e:
            raise (_map_42501(e) or e) from e
    return await get(session, novo_id)
