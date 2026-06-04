"""Schemas da cobrança (Fase 9 — Stripe)."""

import datetime as dt

from pydantic import BaseModel


class CobrancaStatusOut(BaseModel):
    configurado: bool  # o backend tem Stripe configurado? (senão a UI esconde assinar/gerenciar)
    plano: str  # plano efetivo atual (free/pro) — fonte: tenant_assinaturas/plano_do_tenant
    status: str | None = None  # status da subscription no Stripe (active/past_due/canceled…)
    current_period_end: dt.datetime | None = None
    tem_assinatura: bool = False  # há subscription ativa/em graça → mostra "Gerenciar"


class CheckoutOut(BaseModel):
    url: str  # URL hospedada do Stripe (Checkout ou Customer Portal) p/ redirecionar
