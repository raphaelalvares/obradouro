"""Serviço do Catálogo (Livro de referências · Fatia 1). ARQUITETO-ONLY via RLS self (tenant_id =
auth.uid()) — a biblioteca é do dono da conta; membros de obra/projeto não a acessam.

MATEMÁTICA (fonte única): o catálogo guarda custo UNITÁRIO; o orçamento guarda subtotal por linha.
- promover (linha→catálogo): custo_unit = subtotal / qtd  (qtd ausente/0 → trata como 1).
- aplicar (Fatia 2, catálogo→orçamento): subtotal = custo_unit × qtd.
Unitário em 4 casas (numeric(14,4)) reduz drift; o subtotal arredonda a 2 casas ao gravar.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.catalogo import _CUSTO_MAX, PromoverServicoIn, ServicoCreate, ServicoUpdate
from app.services.checklist_import import norm_nome

_COLS = (
    "id, descricao, unidade, custo_mo, custo_material, custo_equipamento, "
    "etapa_sugerida, ativo, created_at, updated_at"
)
_PATCH_COLS = (
    "descricao", "unidade", "custo_mo", "custo_material", "custo_equipamento",
    "etapa_sugerida", "ativo",
)


def _map_42501(e: DBAPIError) -> HTTPException | None:
    if getattr(getattr(e, "orig", None), "sqlstate", None) == "42501":
        return HTTPException(status.HTTP_403_FORBIDDEN, "sem permissão para esta ação")
    return None


# ============================ matemática (pura, testável) ============================
def _custo_unit(valor: float | None, quantidade: float | None) -> float:
    """Custo unitário a partir de um subtotal de linha. qtd ausente ou <=0 → divide por 1 (a linha
    inteira vira o 'unitário', ex.: verba). Arredonda a 4 casas (escala do numeric).

    NB: o unitário é REFERÊNCIA. Re-aplicar (subtotal = unit×qtd) reproduz o subtotal original em
    centavos só p/ qtd pequena/moderada; p/ qtd grande/fracionária o desvio é limitado por ~qtd×5e-5
    (erro de arredondamento das 4 casas) — aceitável p/ estimativa, não é valor contábil."""
    q = quantidade if (quantidade is not None and quantidade > 0) else 1.0
    return round((valor or 0.0) / q, 4)


def _custos_unit(
    valor_mo: float, valor_material: float, valor_equipamento: float, quantidade: float | None
) -> tuple[float, float, float]:
    """Os 3 unitários a partir dos subtotais + qtd, VALIDADOS contra o teto do numeric(14,4) → 422
    (não 500). Dividir por qtd < 1 pode estourar o teto mesmo com os valores dentro dele."""
    cmo = _custo_unit(valor_mo, quantidade)
    cmat = _custo_unit(valor_material, quantidade)
    ceq = _custo_unit(valor_equipamento, quantidade)
    if max(cmo, cmat, ceq) > _CUSTO_MAX:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "custo unitário acima do limite — revise valor e quantidade",
        )
    return cmo, cmat, ceq


# ============================ leitura ============================
async def listar(session: AsyncSession, incluir_inativos: bool = False) -> list[dict]:
    cond = "" if incluir_inativos else "and ativo = true"
    rows = (
        await session.execute(
            text(
                f"select {_COLS} from public.servicos_catalogo "
                f"where tenant_id = (select auth.uid()) {cond} order by descricao"
            )
        )
    ).all()
    return [dict(r._mapping) for r in rows]


async def _get(session: AsyncSession, servico_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            text(
                f"select {_COLS} from public.servicos_catalogo "
                "where id = cast(:i as uuid) and tenant_id = (select auth.uid())"
            ),
            {"i": str(servico_id)},
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "serviço não encontrado")
    return dict(row._mapping)


# ============================ escrita ============================
async def criar(session: AsyncSession, user_id: str, data: ServicoCreate) -> dict:
    nn = norm_nome(data.descricao)
    if not nn:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "descrição inválida")
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    """
                    insert into public.servicos_catalogo
                      (id, tenant_id, descricao, descricao_norm, unidade, custo_mo, custo_material,
                       custo_equipamento, etapa_sugerida, created_by)
                    values (cast(:id as uuid), (select auth.uid()), :descricao, :nn, :unidade,
                            :cmo, :cmat, :ceq, :etapa, (select auth.uid()))
                    """
                ),
                {
                    "id": str(data.id), "descricao": data.descricao, "nn": nn,
                    "unidade": data.unidade, "cmo": data.custo_mo, "cmat": data.custo_material,
                    "ceq": data.custo_equipamento, "etapa": data.etapa_sugerida,
                },
            )
    except IntegrityError as e:
        # (tenant, descricao_norm) único → já existe um serviço com esse nome
        raise HTTPException(
            status.HTTP_409_CONFLICT, "já existe um serviço com esse nome no catálogo"
        ) from e
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    return await _get(session, data.id)


async def atualizar(
    session: AsyncSession, user_id: str, servico_id: uuid.UUID, data: ServicoUpdate
) -> dict:
    await _get(session, servico_id)  # 404 se não for do tenant
    fields = {
        k: v for k, v in data.model_dump(exclude_unset=True).items() if k in _PATCH_COLS
    }
    if not fields:
        return await _get(session, servico_id)
    sets = [f"{k} = :{k}" for k in fields]
    params = dict(fields)
    if "descricao" in fields:
        params["nn"] = norm_nome(fields["descricao"])
        if not params["nn"]:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "descrição inválida")
        sets.append("descricao_norm = :nn")
    params["i"] = str(servico_id)
    try:
        async with session.begin_nested():
            await session.execute(
                text(
                    f"update public.servicos_catalogo set {', '.join(sets)} "
                    "where id = cast(:i as uuid) and tenant_id = (select auth.uid())"
                ),
                params,
            )
    except IntegrityError as e:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "já existe um serviço com esse nome no catálogo"
        ) from e
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    return await _get(session, servico_id)


async def excluir(session: AsyncSession, user_id: str, servico_id: uuid.UUID) -> None:
    await _get(session, servico_id)  # 404 se não for do tenant
    # proteção de uso no SERVICE (o FK p/ template é CASCADE p/ não travar a exclusão de conta —
    # ver 0064): se o serviço está em algum template, NÃO exclui (senão sumiria da receita).
    usado = (
        await session.execute(
            text(
                "select 1 from public.ambiente_template_itens "
                "where servico_id = cast(:i as uuid) and tenant_id = (select auth.uid()) limit 1"
            ),
            {"i": str(servico_id)},
        )
    ).first()
    if usado is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "serviço usado em um template — remova-o do template antes de excluir",
        )
    try:
        await session.execute(
            text(
                "delete from public.servicos_catalogo "
                "where id = cast(:i as uuid) and tenant_id = (select auth.uid())"
            ),
            {"i": str(servico_id)},
        )
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e


async def promover(session: AsyncSession, user_id: str, data: PromoverServicoIn) -> dict:
    """'Salvar no catálogo' a partir de uma linha de orçamento. Calcula o unitário e faz MERGE por
    descricao_norm (atualiza a referência se já existir). Retorna o serviço + se foi criado."""
    nn = norm_nome(data.descricao)
    if not nn:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "descrição inválida")
    cmo, cmat, ceq = _custos_unit(
        data.valor_mo, data.valor_material, data.valor_equipamento, data.quantidade
    )
    # criado vs atualizado: pré-check por nome_norm (ação single-user; sem corrida prática). Mesmo
    # numa corrida, o upsert abaixo grava o dado certo — só o flag 'criado' seria cosmético.
    ja = (
        await session.execute(
            text(
                "select 1 from public.servicos_catalogo "
                "where tenant_id = (select auth.uid()) and descricao_norm = :nn"
            ),
            {"nn": nn},
        )
    ).first()
    criado = ja is None
    try:
        # tabela SEM trigger de seq → ON CONFLICT é seguro (não queima sequencial). Savepoint isola
        # o request de qualquer erro de DB (a validação acima já barra overflow do numeric).
        async with session.begin_nested():
            row = (
                await session.execute(
                    text(
                        """
                        insert into public.servicos_catalogo
                          (id, tenant_id, descricao, descricao_norm, unidade, custo_mo,
                           custo_material, custo_equipamento, etapa_sugerida, created_by)
                        values (gen_random_uuid(), (select auth.uid()), :descricao, :nn, :unidade,
                                :cmo, :cmat, :ceq, :etapa, (select auth.uid()))
                        on conflict (tenant_id, descricao_norm) do update set
                          unidade = excluded.unidade,
                          custo_mo = excluded.custo_mo,
                          custo_material = excluded.custo_material,
                          custo_equipamento = excluded.custo_equipamento,
                          etapa_sugerida = coalesce(excluded.etapa_sugerida,
                                                    public.servicos_catalogo.etapa_sugerida),
                          ativo = true
                        returning id
                        """
                    ),
                    {
                        "descricao": data.descricao, "nn": nn, "unidade": data.unidade,
                        "cmo": cmo, "cmat": cmat, "ceq": ceq, "etapa": data.etapa_sugerida,
                    },
                )
            ).first()
    except DBAPIError as e:
        raise (_map_42501(e) or e) from e
    servico = await _get(session, row.id)
    servico["criado"] = criado
    return servico
