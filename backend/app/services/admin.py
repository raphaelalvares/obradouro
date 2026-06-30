"""Serviço do painel de admin da plataforma.

Lê/escreve CROSS-TENANT via funções SECURITY DEFINER (public.admin_*), cada uma gateada por
is_platform_admin() no banco. A 1ª camada (dependency da rota) já barra não-admin com 403 limpo;
estas funções são a 2ª camada (defesa em profundidade, consistente com a RLS do projeto).
"""

import datetime as dt
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def is_admin(session: AsyncSession) -> bool:
    return bool((await session.execute(text("select public.is_platform_admin()"))).scalar())


def _jsonb(v: object) -> dict:
    """asyncpg devolve jsonb como texto às vezes; normaliza p/ dict."""
    if isinstance(v, str):
        return json.loads(v) or {}
    return v or {}


async def listar_tenants(session: AsyncSession) -> list[dict]:
    rows = (await session.execute(text("select * from public.admin_listar_tenants()"))).mappings()
    return [dict(r) for r in rows]


async def listar_planos(session: AsyncSession) -> list[dict]:
    rows = (await session.execute(text("select * from public.admin_listar_planos()"))).mappings()
    return [
        {**dict(r), "limites": _jsonb(r["limites"]), "flags": _jsonb(r["flags"])} for r in rows
    ]


async def planos_historico(session: AsyncSession, tenant_id: str) -> list[dict]:
    rows = (
        await session.execute(
            text("select * from public.admin_planos_historico(cast(:t as uuid))"), {"t": tenant_id}
        )
    ).mappings()
    return [dict(r) for r in rows]


async def pagamentos(session: AsyncSession, tenant_id: str) -> list[dict]:
    rows = (
        await session.execute(
            text("select * from public.admin_pagamentos(cast(:t as uuid))"), {"t": tenant_id}
        )
    ).mappings()
    return [dict(r) for r in rows]


async def churn(session: AsyncSession, dias: int = 30) -> int:
    return int(
        (await session.execute(text("select public.admin_churn(:d)"), {"d": dias})).scalar() or 0
    )


# --------------------------------------------------------------------- auditoria
async def log(
    session: AsyncSession, acao: str, tenant_id: str | None, detalhe: dict | None = None
) -> None:
    """Registra uma ação do admin (rotas que tocam GoTrue/cobrança fora das funções SQL)."""
    await session.execute(
        text("select public.admin_log_registrar(:a, cast(:t as uuid), cast(:d as jsonb))"),
        {"a": acao, "t": tenant_id, "d": json.dumps(detalhe or {})},
    )


async def log_listar(session: AsyncSession, limit: int = 100) -> list[dict]:
    rows = (
        await session.execute(text("select * from public.admin_log_listar(:n)"), {"n": limit})
    ).mappings()
    return [{**dict(r), "detalhe": _jsonb(r["detalhe"])} for r in rows]


# --------------------------------------------------------------------- notificação de novo cadastro
async def novos_count(session: AsyncSession) -> int:
    return int((await session.execute(text("select public.admin_novos_count()"))).scalar() or 0)


async def marcar_vistos(session: AsyncSession) -> None:
    await session.execute(text("select public.admin_marcar_vistos()"))


# --------------------------------------------------------------------- notas internas
async def notas_listar(session: AsyncSession, tenant_id: str) -> list[dict]:
    rows = (
        await session.execute(
            text("select * from public.admin_notas_listar(cast(:t as uuid))"), {"t": tenant_id}
        )
    ).mappings()
    return [dict(r) for r in rows]


async def nota_criar(session: AsyncSession, tenant_id: str, texto: str) -> None:
    await session.execute(
        text("select public.admin_nota_criar(cast(:t as uuid), :x)"),
        {"t": tenant_id, "x": texto},
    )


async def nota_excluir(session: AsyncSession, nota_id: str) -> None:
    await session.execute(
        text("select public.admin_nota_excluir(cast(:i as uuid))"), {"i": nota_id}
    )


# ------------------------------------------------------------- acessos de cliente (cross-tenant)
async def listar_acessos(session: AsyncSession, tenant_id: str) -> list[dict]:
    rows = (
        await session.execute(
            text("select * from public.admin_listar_acessos_cliente(cast(:t as uuid))"),
            {"t": tenant_id},
        )
    ).mappings()
    return [dict(r) for r in rows]


async def listar_alvos(session: AsyncSession, tenant_id: str) -> list[dict]:
    rows = (
        await session.execute(
            text("select * from public.admin_listar_alvos(cast(:t as uuid))"), {"t": tenant_id}
        )
    ).mappings()
    return [dict(r) for r in rows]


async def autorizar_acesso(
    session: AsyncSession, projeto_id: str | None, obra_id: str | None, email: str
) -> None:
    await session.execute(
        text("select public.admin_autorizar_acesso(cast(:p as uuid), cast(:o as uuid), :e)"),
        {"p": projeto_id, "o": obra_id, "e": email},
    )


async def revogar_acesso(session: AsyncSession, acesso_id: str) -> None:
    await session.execute(
        text("select public.admin_revogar_acesso(cast(:i as uuid))"), {"i": acesso_id}
    )


async def definir_plano(
    session: AsyncSession, tenant_id: str, plano: str, meses: int | None, observacao: str | None
) -> None:
    await session.execute(
        text("select public.admin_definir_plano(cast(:t as uuid), :p, :m, :o)"),
        {"t": tenant_id, "p": plano, "m": meses, "o": observacao},
    )


async def renovar(session: AsyncSession, tenant_id: str, meses: int) -> None:
    await session.execute(
        text("select public.admin_renovar_plano(cast(:t as uuid), :m)"),
        {"t": tenant_id, "m": meses},
    )


async def revogar(session: AsyncSession, tenant_id: str) -> None:
    await session.execute(
        text("select public.admin_revogar_plano(cast(:t as uuid))"), {"t": tenant_id}
    )


async def upsert_plano(session: AsyncSession, codigo: str, data: dict) -> None:
    await session.execute(
        text(
            "select public.admin_upsert_plano(:c, :nome, cast(:lim as jsonb), cast(:fl as jsonb),"
            " :preco, :ativo, :ordem, :sp)"
        ),
        {
            "c": codigo,
            "nome": data["nome"],
            "lim": json.dumps(data.get("limites") or {}),
            "fl": json.dumps(data.get("flags") or {}),
            "preco": data.get("preco_mensal"),
            "ativo": data.get("ativo", True),
            "ordem": data.get("ordem", 0),
            "sp": data.get("stripe_price_id"),
        },
    )


# --------------------------------------------------------------------- métrica (PURA, testável)
def _fim_vigencia(t: dict) -> dt.datetime | None:
    """Data-fim relevante do tenant: manual usa expira_em; Stripe usa current_period_end."""
    if t.get("origem") == "stripe":
        return t.get("current_period_end")
    return t.get("expira_em")


def metricas(
    tenants: list[dict], precos: dict[str, float], agora: dt.datetime, churn_30d: int = 0
) -> dict:
    """Resumo do topo do painel. PURA (sem DB): recebe `agora`, o mapa preço-por-plano e o churn já
    calculado (vem de admin_churn). MRR = Σ preco_mensal dos pagantes."""
    total = len(tenants)
    pagantes = [t for t in tenants if t.get("plano_codigo") != "free"]
    por_plano: dict[str, int] = {}
    for t in tenants:
        cod = t.get("plano_codigo") or "free"
        por_plano[cod] = por_plano.get(cod, 0) + 1

    em_7 = em_30 = 0
    receita = 0.0
    for t in pagantes:
        receita += float(precos.get(t.get("plano_codigo"), 0) or 0)
        fim = _fim_vigencia(t)
        if fim is None:
            continue
        dias = (fim - agora).total_seconds() / 86400
        if 0 <= dias <= 7:
            em_7 += 1
        if 0 <= dias <= 30:
            em_30 += 1

    novos_mes = sum(
        1
        for t in tenants
        if (c := t.get("created_at")) is not None
        and c.year == agora.year
        and c.month == agora.month
    )

    return {
        "total_clientes": total,
        "pagantes": len(pagantes),
        "por_plano": [{"plano": k, "quantidade": v} for k, v in sorted(por_plano.items())],
        "expirando_7d": em_7,
        "expirando_30d": em_30,
        "receita_mensal_estimada": round(receita, 2),
        "novos_mes": novos_mes,
        "churn_30d": churn_30d,
    }
