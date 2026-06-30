"""Schemas da cobrança (Fase 9 — Stripe)."""

import datetime as dt

from pydantic import BaseModel


class CobrancaStatusOut(BaseModel):
    configurado: bool  # o backend tem Stripe configurado? (senão a UI esconde assinar/gerenciar)
    plano: str  # plano efetivo atual — fonte: tenant_assinaturas/plano_do_tenant
    status: str | None = None  # status da subscription no Stripe (active/past_due/canceled…)
    current_period_end: dt.datetime | None = None
    tem_assinatura: bool = False  # há subscription ativa/em graça → mostra "Gerenciar"
    cancelamento_agendado: bool = False  # cancela no fim do período → "acesso até" + "Reativar"
    assinante_desde: dt.datetime | None = None  # 1ª época paga (histórico)
    ultimo_pagamento_em: dt.datetime | None = None
    ultimo_pagamento_cents: int | None = None


class PlanoAssinavelOut(BaseModel):
    """Plano que o arquiteto pode assinar (ativo + Stripe Price). Espelha planos_assinaveis()."""

    codigo: str
    nome: str
    limites: dict
    flags: dict
    preco_mensal: float | None = None
    ordem: int = 0


class CheckoutIn(BaseModel):
    plano: str | None = None  # qual plano assinar; None → fallback STRIPE_PRICE_PRO (env legado)


class CheckoutOut(BaseModel):
    url: str  # URL hospedada do Stripe (Checkout ou Customer Portal) p/ redirecionar
