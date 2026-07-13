"""Serviço de cobrança (Fase 9 — Stripe). MÓDULO SEPARADO do controle de plano (§5): aqui só os
fatos de billing; o webhook traduz o estado da assinatura → plano_codigo (tenant_assinaturas).

Caminho canônico de SaaS: Stripe **Checkout** (página hospedada, PCI leve) p/ assinar + **Customer
Portal** (hospedado) p/ gerenciar/cancelar + **webhooks** p/ refletir o estado no nosso banco. O
webhook é a FONTE DA VERDADE do plano (nunca confiar no redirect de sucesso).

Billing v2 (0091): MULTI-PLANO (cada plano pago → um Stripe Price; o webhook resolve o plano pelo
price, não mais hardcode 'pro') + LEDGER de pagamentos (invoice.payment_succeeded → valor/data) +
HISTÓRICO de planos (registrado dentro de cobranca_aplicar).

Degrada com graça: sem STRIPE_SECRET_KEY/STRIPE_PRICE_PRO o app segue normal e os endpoints de
cobrança respondem 503 "não configurada". `status()`/`planos_assinaveis()` funcionam sem Stripe.
"""

import datetime as dt
import json
import logging

import stripe
from fastapi import HTTPException
from fastapi import status as http
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.services import notificacoes
from app.services.storage import get_storage

settings = get_settings()
log = logging.getLogger("cria.cobranca")

_MB = 1024 * 1024

# status do Stripe que mantêm o acesso pago (past_due = período de graça antes de cancelar de fato).
_STATUS_PRO = {"active", "trialing", "past_due"}


def _client():
    if not settings.cobranca_configurada:
        raise HTTPException(http.HTTP_503_SERVICE_UNAVAILABLE, "cobrança não configurada")
    stripe.api_key = settings.STRIPE_SECRET_KEY.get_secret_value()
    if settings.STRIPE_API_VERSION:  # pina p/ casar a serialização do webhook e dos retrieve
        stripe.api_version = settings.STRIPE_API_VERSION
    return stripe


def _fatura_pendente_url(cust: str | None) -> str | None:
    """hosted_invoice_url da fatura ABERTA (past_due) → botão "Pagar". Best-effort: nunca derruba a
    página nem o header (o Stripe é opcional e pode oscilar). Só chamado quando faz sentido."""
    if not (settings.cobranca_configurada and cust):
        return None
    try:
        _client()
        abertas = stripe.Invoice.list(customer=cust, status="open", limit=1)
        return abertas.data[0].get("hosted_invoice_url") if abertas.data else None
    except Exception:  # noqa: BLE001 — degradação silenciosa; a UI só perde o link de pagar
        return None


# ============================ leitura (UI) ============================
def _jsonb(v: object) -> dict:
    """asyncpg devolve jsonb como texto; normaliza p/ dict."""
    if isinstance(v, str):
        return json.loads(v) or {}
    return v or {}


async def planos_assinaveis(session: AsyncSession) -> list[dict]:
    """Catálogo que o arquiteto pode assinar (ativos com Stripe Price). Não chama o Stripe."""
    rows = (
        await session.execute(text("select * from public.planos_assinaveis()"))
    ).mappings()
    return [
        {**dict(r), "limites": _jsonb(r["limites"]), "flags": _jsonb(r["flags"])} for r in rows
    ]


async def status(session: AsyncSession) -> dict:
    """Status p/ a tela de conta (não chama o Stripe — só o banco)."""
    plano = (
        await session.execute(
            text("select codigo from public.plano_do_tenant((select auth.uid()))")
        )
    ).scalar() or "free"
    row = (
        await session.execute(
            text(
                "select status, current_period_end, stripe_subscription_id, "
                "cancel_at_period_end, stripe_customer_id "
                "from public.tenant_cobranca where tenant_id = (select auth.uid())"
            )
        )
    ).first()
    pag = (
        await session.execute(
            text(
                "select pago_em, valor_cents from public.cobranca_pagamentos "
                "where tenant_id = (select auth.uid()) order by pago_em desc limit 1"
            )
        )
    ).first()
    assinante_desde = (
        await session.execute(
            text(
                "select min(inicio) from public.tenant_plano_historico "
                "where tenant_id = (select auth.uid()) and plano_codigo <> 'free'"
            )
        )
    ).scalar()
    tem = bool(row and row.stripe_subscription_id and (row.status in _STATUS_PRO))
    # fatura pendente só é buscada (chamada ao Stripe) p/ quem está em past_due — custo restrito aos
    # inadimplentes, não em todo render do header. Alimenta o CTA "Pagar" no banner global.
    fatura_url = (
        _fatura_pendente_url(row.stripe_customer_id)
        if (row and row.status == "past_due")
        else None
    )
    return {
        "configurado": settings.cobranca_configurada,
        "plano": plano,
        "status": row.status if row else None,
        "current_period_end": row.current_period_end if row else None,
        "tem_assinatura": tem,
        # cancelamento agendado (cancel_at_period_end): mantém o acesso até o fim do período pago
        "cancelamento_agendado": bool(tem and row.cancel_at_period_end),
        "assinante_desde": assinante_desde,
        "ultimo_pagamento_em": pag.pago_em if pag else None,
        "ultimo_pagamento_cents": pag.valor_cents if pag else None,
        "fatura_pendente_url": fatura_url,
    }


# ============================ Checkout / Portal ============================
async def _customer_id(session: AsyncSession, user_id: str, email: str | None) -> str:
    """Customer do Stripe do tenant (cria na 1ª vez e guarda). metadata.tenant_id liga de volta."""
    existente = (
        await session.execute(
            text(
                "select stripe_customer_id from public.tenant_cobranca "
                "where tenant_id = (select auth.uid())"
            )
        )
    ).scalar()
    if existente:
        return existente
    cust = stripe.Customer.create(email=email, metadata={"tenant_id": user_id})
    await session.execute(
        text("select public.cobranca_set_customer(cast(:t as uuid), :c)"),
        {"t": user_id, "c": cust.id},
    )
    return cust.id


async def _price_do_plano(session: AsyncSession, plano: str | None) -> str:
    """Stripe Price do plano escolhido. Sem plano → fallback no STRIPE_PRICE_PRO (env legado).
    400 se o plano não for assinável (sem price)."""
    if not plano:
        return settings.STRIPE_PRICE_PRO
    price = (
        await session.execute(
            text("select stripe_price_id from public.planos where codigo = :c and ativo"),
            {"c": plano},
        )
    ).scalar()
    if not price:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "plano indisponível para assinatura")
    return price


async def criar_checkout(
    session: AsyncSession,
    user_id: str,
    email: str | None,
    plano: str | None = None,
    winback: bool = False,
) -> str:
    """Sessão de Checkout (assinatura). Retorna a URL hospedada p/ redirecionar. `winback` = re-
    assinatura de quem caiu p/ free: aplica o cupom (STRIPE_PROMO_WINBACK) SE o tenant for elegível
    (gate server-side — o promo não pode ser auto-aplicado por qualquer um)."""
    _client()
    price = await _price_do_plano(session, plano)
    customer = await _customer_id(session, user_id, email)
    base = settings.app_base_url
    extra: dict = {}
    if winback and settings.STRIPE_PROMO_WINBACK:
        elegivel = (
            await session.execute(
                text("select public.cobranca_elegivel_winback((select auth.uid()))")
            )
        ).scalar()
        if elegivel:
            extra["discounts"] = [{"promotion_code": settings.STRIPE_PROMO_WINBACK}]
    sess = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer,
        line_items=[{"price": price, "quantity": 1}],
        client_reference_id=user_id,
        subscription_data={"metadata": {"tenant_id": user_id}},
        success_url=f"{base}/configuracoes?cobranca=sucesso",
        cancel_url=f"{base}/configuracoes?cobranca=cancelado",
        **extra,
    )
    return sess.url


async def criar_portal(session: AsyncSession, user_id: str) -> str:
    """Sessão do Customer Portal (gerenciar/cancelar). 409 se o tenant ainda não tem customer."""
    _client()
    customer = (
        await session.execute(
            text(
                "select stripe_customer_id from public.tenant_cobranca "
                "where tenant_id = (select auth.uid())"
            )
        )
    ).scalar()
    if not customer:
        raise HTTPException(http.HTTP_409_CONFLICT, "sem assinatura para gerenciar")
    sess = stripe.billing_portal.Session.create(
        customer=customer, return_url=f"{settings.app_base_url}/configuracoes"
    )
    return sess.url


# ============================ Cancelar / reativar (self-service) ============================
async def _subscription_id(session: AsyncSession) -> str:
    """Subscription do tenant corrente; 409 se não houver o que cancelar/reativar."""
    sub = (
        await session.execute(
            text(
                "select stripe_subscription_id from public.tenant_cobranca "
                "where tenant_id = (select auth.uid())"
            )
        )
    ).scalar()
    if not sub:
        raise HTTPException(http.HTTP_409_CONFLICT, "sem assinatura para gerenciar")
    return sub


async def cancelar_assinatura(session: AsyncSession, user_id: str) -> dict:
    """Agenda o cancelamento p/ o FIM do período pago (cancel_at_period_end). O acesso segue até lá;
    o webhook derruba pro free quando a subscription for deletada. Espelha o flag p/ a UI refletir
    na hora (o webhook reconcilia em seguida)."""
    _client()
    sub = await _subscription_id(session)
    stripe.Subscription.modify(sub, cancel_at_period_end=True)
    await session.execute(
        text("select public.cobranca_set_cancelamento(cast(:t as uuid), true)"), {"t": user_id}
    )
    return await status(session)


async def reativar_assinatura(session: AsyncSession, user_id: str) -> dict:
    """Desfaz o cancelamento agendado (volta a renovar no fim do período)."""
    _client()
    sub = await _subscription_id(session)
    stripe.Subscription.modify(sub, cancel_at_period_end=False)
    await session.execute(
        text("select public.cobranca_set_cancelamento(cast(:t as uuid), false)"), {"t": user_id}
    )
    return await status(session)


# ============================ Webhook ============================
def _ts(epoch: int | None) -> dt.datetime | None:
    return dt.datetime.fromtimestamp(epoch, tz=dt.UTC) if epoch else None


def _plan_price_id(obj: dict, storage_price: str | None) -> str | None:
    """Price do item de PLANO da assinatura, IGNORANDO o item de armazenamento (add-on). Robusto a
    múltiplos itens: pega o 1º que não seja o storage; se só houver storage, cai no 1º item."""
    itens = ((obj.get("items") or {}).get("data")) or []
    nao_storage = [i for i in itens if ((i.get("price") or {}).get("id")) != storage_price]
    escolhido = nao_storage[0] if nao_storage else (itens[0] if itens else None)
    return ((escolhido.get("price") or {}).get("id")) if escolhido else None


def _item_storage(obj: dict, storage_price: str | None) -> tuple[str | None, int]:
    """(item_id, quantity) do item de ARMAZENAMENTO na assinatura, ou (None, 0). `obj` é o objeto da
    subscription (do webhook OU do Stripe.Subscription.retrieve — ambos dict-like em .get)."""
    if not storage_price:
        return (None, 0)
    for i in ((obj.get("items") or {}).get("data")) or []:
        if ((i.get("price") or {}).get("id")) == storage_price:
            return (i.get("id"), int(i.get("quantity") or 0))
    return (None, 0)


def _period_end_sub(obj: dict, storage_price: str | None) -> int | None:
    """Fim do período pago (epoch) da subscription. Na API Basil (2025-03-31+) o campo saiu do TOPO
    do objeto e passou a viver no ITEM do plano (items.data[].current_period_end). Lê de lá com
    fallback no topo (compat versões antigas). Ignora o item de storage. None se não achar."""
    top = obj.get("current_period_end")
    if top:
        return top
    itens = ((obj.get("items") or {}).get("data")) or []
    nao_storage = [i for i in itens if ((i.get("price") or {}).get("id")) != storage_price]
    it = nao_storage[0] if nao_storage else (itens[0] if itens else None)
    return it.get("current_period_end") if it else None


def _price_id_invoice(obj: dict) -> str | None:
    linhas = ((obj.get("lines") or {}).get("data")) or []
    return ((linhas[0].get("price") or {}).get("id")) if linhas else None


def mapear_evento(event: dict) -> dict | None:
    """PURA: traduz um evento do Stripe num dict discriminado por `kind` ('subscription' |
    'checkout' | 'payment') ou None se irrelevante. Não resolve plano/tenant que dependam do banco —
    isso fica em `_aplicar` (que tem sessão). tenant_id vem do metadata do checkout (confiável)."""
    tipo = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}
    ev_id = event.get("id")
    ev_em = _ts(event.get("created"))  # p/ a guarda de recência (out-of-order) em cobranca_aplicar

    if tipo.startswith("customer.subscription."):
        meta = obj.get("metadata") or {}
        tenant = meta.get("tenant_id")
        if not tenant:
            return None
        st = "canceled" if tipo.endswith(".deleted") else obj.get("status")
        sp = settings.STRIPE_PRICE_ARMAZENAMENTO
        return {
            "kind": "subscription",
            "event_id": ev_id,
            "evento_em": ev_em,
            "tenant_id": tenant,
            "customer": obj.get("customer"),
            "subscription": obj.get("id"),
            "status": st,
            "period_end": _ts(_period_end_sub(obj, sp)),  # Basil-safe (topo → item do plano)
            "price_id": _plan_price_id(obj, sp),  # price do PLANO (ignora o item de storage)
            "storage_qty": _item_storage(obj, sp)[1],  # GB contratados no add-on de storage
            "cancel_at_period_end": bool(obj.get("cancel_at_period_end")),
        }

    if tipo == "checkout.session.completed":
        tenant = (obj.get("metadata") or {}).get("tenant_id") or obj.get("client_reference_id")
        if not tenant:
            return None
        # confirma o customer/subscription; o plano real vem nos eventos de subscription seguintes.
        return {
            "kind": "checkout",
            "event_id": ev_id,
            "evento_em": ev_em,
            "tenant_id": tenant,
            "customer": obj.get("customer"),
            "subscription": obj.get("subscription"),
        }

    if tipo in ("invoice.payment_succeeded", "invoice.paid"):
        cents = obj.get("amount_paid")
        if not cents:  # 0/None (ex.: fatura de trial sem cobrança) → nada a registrar
            return None
        meta = (obj.get("subscription_details") or {}).get("metadata") or {}
        paid_at = (obj.get("status_transitions") or {}).get("paid_at") or obj.get("created")
        return {
            "kind": "payment",
            "event_id": ev_id,
            "tenant_id": meta.get("tenant_id"),  # pode faltar → resolve por customer no banco
            "customer": obj.get("customer"),
            "invoice_id": obj.get("id"),
            "amount_cents": cents,
            "currency": obj.get("currency") or "brl",
            "paid_at": _ts(paid_at),
            "price_id": _price_id_invoice(obj),
        }

    if tipo == "invoice.payment_failed":  # cartão recusado → jornada de expiry (dunning)
        meta = (obj.get("subscription_details") or {}).get("metadata") or {}
        return {
            "kind": "payment_failed",
            "event_id": ev_id,
            "tenant_id": meta.get("tenant_id"),  # pode faltar → resolve por customer no banco
            "customer": obj.get("customer"),
            "invoice_id": obj.get("id"),
            "amount_cents": obj.get("amount_due"),
            "hosted_invoice_url": obj.get("hosted_invoice_url"),
            "next_attempt": _ts(obj.get("next_payment_attempt")),
        }

    if tipo == "invoice.upcoming":  # pré-renovação (aviso opcional; gate COBRANCA_AVISO_RENOVACAO)
        meta = (obj.get("subscription_details") or {}).get("metadata") or {}
        return {
            "kind": "upcoming",
            "event_id": ev_id,
            "tenant_id": meta.get("tenant_id"),
            "customer": obj.get("customer"),
            "amount_cents": obj.get("amount_due"),
            "period_end": _ts(obj.get("period_end")),  # ~ data da próxima cobrança
        }

    return None


async def _plano_por_price(session: AsyncSession, price_id: str | None) -> str | None:
    if not price_id:
        return None
    return (
        await session.execute(
            text("select public.plano_por_price(:p)"), {"p": price_id}
        )
    ).scalar()


async def _contato(
    session: AsyncSession, tenant_id: str | None, customer: str | None
) -> tuple[str | None, str | None, str | None]:
    """(tenant_id, email, nome) do arquiteto p/ um aviso. Resolve por tenant (metadata) e, faltando,
    por customer (algumas invoices não trazem o tenant no metadata). Roda no webhook (cria_app)."""
    if tenant_id:
        r = (
            await session.execute(
                text("select email, nome from public.cobranca_contato(cast(:t as uuid))"),
                {"t": tenant_id},
            )
        ).first()
        if r:
            return (tenant_id, r.email, r.nome)
    if customer:
        r = (
            await session.execute(
                text("select tenant_id, email, nome from public.cobranca_contato_por_customer(:c)"),
                {"c": customer},
            )
        ).first()
        if r:
            return (str(r.tenant_id), r.email, r.nome)
    return (None, None, None)


async def _reivindicar_aviso(session: AsyncSession, tenant: str, tipo: str, chave: str) -> bool:
    """Reivindica o envio de um aviso (dedupe): True só na 1ª vez p/ esta chave (re-entrega do
    Stripe → False → não reenvia). Commitado com o estado; o envio é best-effort após o commit."""
    return bool(
        (
            await session.execute(
                text("select public.cobranca_aviso_uma_vez(cast(:t as uuid), :tp, :ch)"),
                {"t": tenant, "tp": tipo, "ch": chave},
            )
        ).scalar()
    )


async def _aplicar(session: AsyncSession, dados: dict) -> list[dict]:
    """Aplica o evento no banco (resoluções que dependem do DB) e devolve os AVISOS a enviar DEPOIS
    do commit — cada um já com destinatário resolvido e reivindicado (dedupe anti-reentrega)."""
    kind = dados["kind"]

    if kind == "payment":
        plano = await _plano_por_price(session, dados.get("price_id"))
        await session.execute(
            text(
                "select public.cobranca_registrar_pagamento("
                "cast(:t as uuid), :cust, :inv, :cents, :moeda, :plano, :pago)"
            ),
            {
                "t": dados["tenant_id"],
                "cust": dados["customer"],
                "inv": dados["invoice_id"],
                "cents": dados["amount_cents"],
                "moeda": dados["currency"],
                "plano": plano,
                "pago": dados["paid_at"],
            },
        )
        return []

    if kind == "payment_failed":  # cartão recusado (dunning) → e-mail p/ regularizar
        tenant, email, nome = await _contato(session, dados.get("tenant_id"), dados.get("customer"))
        if not (tenant and email):
            return []
        if not await _reivindicar_aviso(session, tenant, "cartao_recusado", dados["event_id"]):
            return []
        return [
            {
                "tipo": "cartao_recusado",
                "to": email,
                "nome": nome,
                "fatura_url": dados.get("hosted_invoice_url"),
            }
        ]

    if kind == "upcoming":  # aviso opcional de renovação próxima (nasce OFF)
        if not settings.COBRANCA_AVISO_RENOVACAO:
            return []
        tenant, email, nome = await _contato(session, dados.get("tenant_id"), dados.get("customer"))
        if not (tenant and email):
            return []
        if not await _reivindicar_aviso(session, tenant, "renovacao", dados["event_id"]):
            return []
        return [
            {
                "tipo": "renovacao",
                "to": email,
                "nome": nome,
                "valor_cents": dados.get("amount_cents"),
                "quando": dados.get("period_end"),
            }
        ]

    # kind in ('subscription', 'checkout')
    if kind == "subscription":
        st = dados["status"]
        plano = (await _plano_por_price(session, dados.get("price_id")) or "pro") \
            if st in _STATUS_PRO else "free"
        period_end = dados.get("period_end")
    else:  # checkout: só confirma customer/subscription; plano vem nos eventos de subscription
        st = None
        plano = None
        period_end = None

    aplicou = bool(
        (
            await session.execute(
                text(
                    "select public.cobranca_aplicar("
                    "cast(:t as uuid), :c, :s, :st, :pe, :pl, :ev)"
                ),
                {
                    "t": dados["tenant_id"],
                    "c": dados["customer"],
                    "s": dados["subscription"],
                    "st": st,
                    "pe": period_end,
                    "pl": plano,
                    "ev": dados.get("evento_em"),
                },
            )
        ).scalar()
    )

    # checkout não espelha nada; um evento STALE (aplicou=false) não regride cancelamento/storage.
    if kind != "subscription" or not aplicou:
        return []

    # espelha o agendamento de cancelamento (só faz sentido enquanto a assinatura está ativa)
    agendado = bool(dados.get("cancel_at_period_end")) and st in _STATUS_PRO
    await session.execute(
        text("select public.cobranca_set_cancelamento(cast(:t as uuid), :c)"),
        {"t": dados["tenant_id"], "c": agendado},
    )
    # cota CONTRATADA = quantidade do item de storage (0 se perdeu a assinatura → sem add-on).
    contratado_mb = (dados.get("storage_qty") or 0) * 1024 if st in _STATUS_PRO else 0
    await session.execute(
        text("select public.cobranca_set_armazenamento_contratado(cast(:t as uuid), :mb)"),
        {"t": dados["tenant_id"], "mb": contratado_mb},
    )

    # aviso de "cancelamento agendado" (1x por período; re-agendou p/ outro período → re-avisa)
    intents: list[dict] = []
    fim = dados.get("period_end")
    if agendado and fim:
        tenant, email, nome = await _contato(session, dados["tenant_id"], dados.get("customer"))
        chave = f"{dados.get('subscription')}:{fim.isoformat()}"
        if email and await _reivindicar_aviso(session, tenant, "cancelamento", chave):
            intents.append({"tipo": "cancelamento", "to": email, "nome": nome, "quando": fim})
    return intents


async def _despachar_avisos(intents: list[dict]) -> None:
    """Envia os avisos de billing DEPOIS do commit (best-effort — nunca derruba o webhook, que já
    persistiu o estado + reivindicou o dedupe). Cada tipo → uma função de notificacoes."""
    for it in intents:
        try:
            tipo = it["tipo"]
            if tipo == "cartao_recusado":
                await notificacoes.notificar_pagamento_falhou(
                    to=it["to"], nome=it["nome"], fatura_url=it.get("fatura_url")
                )
            elif tipo == "cancelamento":
                await notificacoes.notificar_cancelamento_agendado(
                    to=it["to"], nome=it["nome"], quando=it["quando"]
                )
            elif tipo == "renovacao":
                await notificacoes.notificar_renovacao_proxima(
                    to=it["to"],
                    nome=it["nome"],
                    valor_cents=it.get("valor_cents"),
                    quando=it.get("quando"),
                )
        except Exception:  # noqa: BLE001 — aviso é reforço; nunca propaga p/ o webhook
            log.exception("falha ao despachar aviso de billing (%s)", it.get("tipo"))


async def processar_webhook(payload: bytes, sig: str | None) -> dict:
    """Verifica a assinatura, traduz o evento e aplica no banco (via funções SECURITY DEFINER, fora
    do contexto authenticated). Idempotente: reprocessar o mesmo evento converge ao mesmo estado (o
    dedupe de avisos evita e-mail duplicado na re-entrega). Avisos saem DEPOIS do commit."""
    if not settings.cobranca_configurada or not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(http.HTTP_503_SERVICE_UNAVAILABLE, "cobrança não configurada")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig or "", settings.STRIPE_WEBHOOK_SECRET.get_secret_value()
        )
    except (ValueError, stripe.SignatureVerificationError) as e:
        raise HTTPException(http.HTTP_400_BAD_REQUEST, "assinatura do webhook inválida") from e

    dados = mapear_evento(event if isinstance(event, dict) else event.to_dict_recursive())
    if dados is None:
        return {"ignored": True}

    async with SessionLocal() as session:
        async with session.begin():
            intents = await _aplicar(session, dados)
    await _despachar_avisos(intents)
    return {"ok": True}


# ============================ Financeiro / add-on de armazenamento ============================
def proration_estimada(
    preco_gb_centavos: int, delta_gb: int, period_end: dt.datetime | None, agora: dt.datetime
) -> int:
    """PURA: estima (centavos) o pro-rata de um AUMENTO de `delta_gb` GB até `period_end`. Só p/ o
    texto de confirmação (o valor cobrado é o do Stripe). Reduções/sem período → 0. Ciclo ~30d."""
    if delta_gb <= 0 or period_end is None:
        return 0
    restante = (period_end - agora).total_seconds()
    if restante <= 0:
        return 0
    fracao = min(1.0, restante / (30 * 86400))
    return round(delta_gb * preco_gb_centavos * fracao)


async def _pool_livre_mb(session: AsyncSession) -> int | None:
    """MB livres p/ contratar no pool físico (total − comprometido). None = sem teto conhecido (dev/
    backend local) → sem gate. Usa STORAGE_POOL_MB ou o total real da conta (Drive)."""
    if settings.STORAGE_POOL_MB is not None:
        total_mb = settings.STORAGE_POOL_MB
    else:
        try:
            conta = await get_storage().espaco_conta()
        except Exception:  # noqa: BLE001 — medir a conta nunca deve bloquear a contratação
            conta = None
        if not conta or conta.get("total_bytes") is None:
            return None
        total_mb = int(conta["total_bytes"]) // _MB
    comprometido = int(
        (
            await session.execute(text("select public.armazenamento_comprometido_total_mb()"))
        ).scalar()
        or 0
    )
    return total_mb - comprometido


async def contratar_armazenamento(session: AsyncSession, user_id: str, gb_total: int) -> dict:
    """Self-service: define o TOTAL de GB do add-on de storage na assinatura do arquiteto. Cobra o
    pro-rata na hora (always_invoice) e o valor cheio no próximo ciclo. 0 cancela o add-on. Exige
    assinatura ATIVA (o item recorrente vive dentro dela). Devolve o Financeiro atualizado."""
    _client()
    if not settings.STRIPE_PRICE_ARMAZENAMENTO:
        raise HTTPException(http.HTTP_503_SERVICE_UNAVAILABLE, "armazenamento não configurado")
    gb_total = max(0, int(gb_total))

    row = (
        await session.execute(
            text(
                "select stripe_subscription_id, status from public.tenant_cobranca "
                "where tenant_id = (select auth.uid())"
            )
        )
    ).first()
    if not row or not row.stripe_subscription_id or row.status not in _STATUS_PRO:
        raise HTTPException(http.HTTP_409_CONFLICT, "assine um plano para ampliar o espaço")

    # contratado atual + gate de pool (só barra AUMENTO acima do que cabe fisicamente)
    arm = (await session.execute(text("select * from public.meu_armazenamento()"))).first()
    contratado_atual_mb = int(arm.contratado_mb) if arm else 0
    delta_mb = gb_total * 1024 - contratado_atual_mb
    if delta_mb > 0:
        livre = await _pool_livre_mb(session)
        if livre is not None and delta_mb > livre:
            raise HTTPException(http.HTTP_409_CONFLICT, "sem espaço disponível no momento")

    sub = stripe.Subscription.retrieve(row.stripe_subscription_id)
    item_id, _q = _item_storage(sub, settings.STRIPE_PRICE_ARMAZENAMENTO)
    if gb_total == 0:
        if item_id:
            stripe.SubscriptionItem.delete(item_id, proration_behavior="always_invoice")
    elif item_id:
        stripe.SubscriptionItem.modify(
            item_id, quantity=gb_total, proration_behavior="always_invoice"
        )
    else:
        stripe.SubscriptionItem.create(
            subscription=row.stripe_subscription_id,
            price=settings.STRIPE_PRICE_ARMAZENAMENTO,
            quantity=gb_total,
            proration_behavior="always_invoice",
        )

    # reflete a cota já (UX imediata); o webhook de subscription.updated reconcilia idempotente.
    await session.execute(
        text("select public.cobranca_set_armazenamento_contratado(cast(:t as uuid), :mb)"),
        {"t": user_id, "mb": gb_total * 1024},
    )
    return await financeiro(session, user_id)


async def financeiro(session: AsyncSession, user_id: str) -> dict:
    """Área de Financeiro do assinante: plano + add-on de storage + faturas. Degrada sem Stripe (só
    não traz a fatura pendente hospedada)."""
    st = await status(session)
    arm = (await session.execute(text("select * from public.meu_armazenamento()"))).first()
    usado = (
        await session.execute(text("select public.meu_consumo_armazenamento_bytes()"))
    ).scalar() or 0
    pags = (
        (
            await session.execute(
                text(
                    "select valor_cents, moeda, plano_codigo, pago_em "
                    "from public.cobranca_pagamentos where tenant_id = (select auth.uid()) "
                    "order by pago_em desc limit 24"
                )
            )
        )
        .mappings()
        .all()
    )
    cust = (
        await session.execute(
            text(
                "select stripe_customer_id from public.tenant_cobranca "
                "where tenant_id = (select auth.uid())"
            )
        )
    ).scalar()

    fatura_url = _fatura_pendente_url(cust)

    base_mb = int(arm.base_mb) if arm else 0
    contratado_mb = int(arm.contratado_mb) if arm else 0
    contratado_gb = contratado_mb // 1024
    preco_gb = settings.ARMAZENAMENTO_PRECO_GB_CENTAVOS
    return {
        "configurado": st["configurado"],
        "plano": st["plano"],
        "status": st["status"],
        "current_period_end": st["current_period_end"],
        "tem_assinatura": st["tem_assinatura"],
        "cancelamento_agendado": st["cancelamento_agendado"],
        "assinante_desde": st["assinante_desde"],
        "pode_gerenciar": bool(cust),
        "fatura_pendente_url": fatura_url,
        "armazenamento": {
            "base_mb": base_mb,
            "extra_mb": int(arm.extra_mb) if arm else 0,
            "contratado_mb": contratado_mb,
            "efetivo_mb": int(arm.efetivo_mb) if arm else base_mb,
            "usado_bytes": int(usado),
            "contratado_gb": contratado_gb,
            "preco_gb_centavos": preco_gb,
            "mensal_cents": contratado_gb * preco_gb,
            "configuravel": settings.armazenamento_configurado,
        },
        "pagamentos": [dict(p) for p in pags],
    }


# ===================== Win-back (re-sell) — varredura periódica (reaper) =====================
# Dias após a queda p/ free em que se toca o arquiteto. 1 e-mail por estágio (dedupe por marco).
_WINBACK_ESTAGIOS = (1, 7, 30)


def _estagio_winback(dias: int) -> int | None:
    """Maior estágio já ALCANÇADO por `dias` desde a queda (dias=8 → 7; dias=0 → None). O dedupe por
    estágio garante 1 e-mail por marco mesmo que a varredura veja o candidato dias depois."""
    alcancados = [e for e in _WINBACK_ESTAGIOS if dias >= e]
    return max(alcancados) if alcancados else None


async def cobranca_tick() -> int:
    """Uma passada do reaper de cobrança: varre quem caiu p/ free (e segue free) e manda o e-mail de
    win-back do estágio devido (1x por estágio, via dedupe). Roda como cria_app (sem JWT). No-op sem
    Resend (não há canal). Retorna quantos e-mails enviou. Best-effort por candidato."""
    if not settings.email_configurado:
        return 0
    com_cupom = bool(settings.STRIPE_PROMO_WINBACK)
    async with SessionLocal() as session:
        cands = (
            (
                await session.execute(
                    text("select * from public.cobranca_winback_candidatos(:d, :lim)"),
                    {
                        "d": settings.COBRANCA_WINBACK_MAX_DIAS,
                        "lim": settings.COBRANCA_WINBACK_BATCH,
                    },
                )
            )
            .mappings()
            .all()
        )

    enviados = 0
    for c in cands:
        if not c["email"]:
            continue
        estagio = _estagio_winback(int(c["dias"]))
        if estagio is None:
            continue
        # reivindica o estágio numa transação curta própria (dedupe commitado antes do envio)
        async with SessionLocal() as session:
            async with session.begin():
                deve = bool(
                    (
                        await session.execute(
                            text(
                                "select public.cobranca_aviso_uma_vez("
                                "cast(:t as uuid), 'winback', :ch)"
                            ),
                            {"t": str(c["tenant_id"]), "ch": f"d{estagio}"},
                        )
                    ).scalar()
                )
        if not deve:
            continue
        try:
            await notificacoes.notificar_winback(
                to=c["email"], nome=c["nome"], com_cupom=com_cupom
            )
            enviados += 1
        except Exception:  # noqa: BLE001 — best-effort; um envio ruim não trava a varredura
            log.exception("win-back: falha ao enviar (tenant %s)", c["tenant_id"])

    enviados += await _tick_upsell_storage()
    return enviados


async def _tick_upsell_storage() -> int:
    """Up-sell de GB: assinantes pagos que encostaram no limite → e-mail p/ contratar mais espaço
    (throttle periódico p/ re-lembrar sem spammar). Só se o add-on está configurável no Stripe."""
    if not settings.armazenamento_configurado:
        return 0
    async with SessionLocal() as session:
        ups = (
            (
                await session.execute(
                    text("select * from public.cobranca_upsell_storage_candidatos(:pct, :lim)"),
                    {
                        "pct": settings.ARMAZENAMENTO_AVISO_PCT,
                        "lim": settings.COBRANCA_WINBACK_BATCH,
                    },
                )
            )
            .mappings()
            .all()
        )
    enviados = 0
    for u in ups:
        if not u["email"]:
            continue
        async with SessionLocal() as session:
            async with session.begin():
                deve = bool(
                    (
                        await session.execute(
                            text(
                                "select public.cobranca_aviso_periodico("
                                "cast(:t as uuid), 'quota', 'cheio', make_interval(days => :d))"
                            ),
                            {"t": str(u["tenant_id"]), "d": settings.ARMAZENAMENTO_REAVISO_DIAS},
                        )
                    ).scalar()
                )
        if not deve:
            continue
        try:
            await notificacoes.notificar_armazenamento_cheio(
                to=u["email"], nome=u["nome"], pct=min(100, int(u["pct"])), contratavel=True
            )
            enviados += 1
        except Exception:  # noqa: BLE001 — best-effort
            log.exception("up-sell storage: falha ao enviar (tenant %s)", u["tenant_id"])
    return enviados
