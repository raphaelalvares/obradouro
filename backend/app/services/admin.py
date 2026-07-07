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


async def definir_armazenamento_extra(session: AsyncSession, tenant_id: str, extra_mb: int) -> None:
    """Aloca (reserva) espaço EXTRA p/ um cliente, acima/abaixo do plano. Pode ser negativo. A
    função SQL já registra na auditoria."""
    await session.execute(
        text("select public.admin_definir_armazenamento_extra(cast(:t as uuid), :e)"),
        {"t": tenant_id, "e": int(extra_mb)},
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


# ----------------------------------------------------------- resumo do POOL de armazenamento (PURO)
_MB = 1024 * 1024


def resumo_armazenamento(
    tenants: list[dict],
    conta: dict | None,
    backend: str,
    pool_override_mb: int | None = None,
    preco_gb_centavos: int = 0,
) -> dict:
    """Resumo do pool de storage p/ o painel admin. PURA (sem DB/rede): recebe a lista de tenants
    (com armazenamento_bytes = consumo CONTABILIZADO, armazenamento_limite_mb = limite EFETIVO e
    armazenamento_contratado_mb = contratado via Stripe) e o espaço da CONTA (de
    get_storage().espaco_conta(); None se o backend não sabe medir).

    Dois eixos, deliberadamente separados (não confundir — foi a origem do 'cálculo errado'):
      • físico   → total/usado/livre REAIS da conta (inclui miniaturas, Gmail, Fotos, lixeira).
      • cotas    → consumo contabilizado (o que cobramos) e COMPROMETIDO (Σ dos limites alocados).
    'livre_para_alocar' = total físico − comprometido; 'overcommit' = prometeu mais do que cabe.
    'receita_contratada_cents' = MRR do add-on (Σ GB contratados × preço/GB)."""

    def limite(t: dict) -> int:
        return int(t.get("armazenamento_limite_mb") or 0)

    def paga(t: dict) -> bool:
        return (t.get("plano_codigo") or "free") != "free"

    consumo = sum(int(t.get("armazenamento_bytes") or 0) for t in tenants)
    ilimitado = any(limite(t) < 0 for t in tenants)
    comprometido_mb = sum(limite(t) for t in tenants if limite(t) > 0)
    comprometido_pag_mb = sum(limite(t) for t in tenants if limite(t) > 0 and paga(t))
    contratado_mb = sum(max(0, int(t.get("armazenamento_contratado_mb") or 0)) for t in tenants)
    receita_cents = (contratado_mb // 1024) * preco_gb_centavos  # GB contratados × preço/GB

    total_bytes = conta.get("total_bytes") if conta else None
    if pool_override_mb is not None:  # override manual (reservar folga sob os 5 TB) tem prioridade
        total_bytes = pool_override_mb * _MB

    comprometido_bytes = comprometido_mb * _MB
    livre_alocar = (total_bytes - comprometido_bytes) if total_bytes is not None else None
    return {
        "backend": backend,
        "conta_disponivel": conta is not None,
        "total_bytes": total_bytes,
        "usado_real_bytes": conta.get("usado_bytes") if conta else None,
        "usado_drive_bytes": conta.get("usado_drive_bytes") if conta else None,
        "lixeira_bytes": conta.get("lixeira_bytes") if conta else None,
        "consumo_contabilizado_bytes": consumo,
        "comprometido_mb": comprometido_mb,
        "comprometido_pagantes_mb": comprometido_pag_mb,
        "contratado_total_mb": contratado_mb,
        "receita_contratada_cents": receita_cents,
        "preco_gb_centavos": preco_gb_centavos,
        "n_clientes": len(tenants),
        "ilimitado_presente": ilimitado,
        "livre_para_alocar_bytes": livre_alocar,
        "overcommit": total_bytes is not None and comprometido_bytes > total_bytes,
    }
