"""Schemas da cobrança (Fase 9 — Stripe)."""

import datetime as dt

from pydantic import BaseModel, Field


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


# ============================ Financeiro (add-on de armazenamento) ============================
class AddOnArmazenamentoOut(BaseModel):
    """Detalhamento do armazenamento do assinante p/ a área de Financeiro."""

    base_mb: int  # o que o PLANO dá (-1 = ilimitado)
    extra_mb: int  # cortesia manual do admin (pode ser ±)
    contratado_mb: int  # contratado via Stripe (self-service, pago)
    efetivo_mb: int  # limite total em vigor (-1 = ilimitado)
    usado_bytes: int  # consumo contabilizado
    contratado_gb: int  # contratado_mb em GB (unidade da cobrança)
    preco_gb_centavos: int  # preço/GB p/ exibir (o cobrado sai do Stripe)
    mensal_cents: int  # quanto o contratado custa por mês (contratado_gb × preço/GB)
    configuravel: bool  # o add-on está configurado no Stripe? (senão UI esconde "contratar")


class PagamentoFinOut(BaseModel):
    valor_cents: int
    moeda: str
    plano_codigo: str | None = None
    pago_em: dt.datetime


class FinanceiroOut(BaseModel):
    """Área de Financeiro do assinante: plano + add-on de storage + faturas."""

    configurado: bool  # Stripe configurado no backend?
    plano: str
    status: str | None = None  # status da subscription (active/past_due/canceled…)
    current_period_end: dt.datetime | None = None
    tem_assinatura: bool = False  # assinatura ativa/em graça (exige p/ contratar add-on)
    cancelamento_agendado: bool = False
    assinante_desde: dt.datetime | None = None
    pode_gerenciar: bool = False  # tem customer/subscription → botão Portal
    fatura_pendente_url: str | None = None  # invoice aberta (hosted_invoice_url) → "Pagar"
    armazenamento: AddOnArmazenamentoOut
    pagamentos: list[PagamentoFinOut] = []


class ContratarArmazenamentoIn(BaseModel):
    """Define o TOTAL de GB contratado (não é delta). 0 = cancela o add-on."""

    gb_total: int = Field(ge=0, le=100_000)  # teto de sanidade (100 TB)
