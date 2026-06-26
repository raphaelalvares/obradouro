"""Schemas do painel de admin da plataforma (dono do SaaS)."""

import datetime as dt
import uuid

from pydantic import BaseModel, Field


class AdminMeOut(BaseModel):
    is_admin: bool  # usado pelo front p/ mostrar/esconder o menu Admin (gateia a UI)


class TenantAdminOut(BaseModel):
    """Espelha public.admin_listar_tenants(). Um 'cliente' do SaaS = uma row de profiles."""

    tenant_id: uuid.UUID
    email: str
    nome: str | None = None
    nome_escritorio: str | None = None
    plano_codigo: str  # plano EFETIVO (respeita expiração)
    plano_nome: str
    origem: str | None = None  # 'manual' | 'stripe' | None (sem assinatura)
    expira_em: dt.datetime | None = None  # validade da concessão manual (None = sem expiração)
    observacao: str | None = None
    cobranca_status: str | None = None  # status da subscription no Stripe (se houver)
    current_period_end: dt.datetime | None = None  # fim do período pago no Stripe (se houver)
    obras_ativas: int = 0
    armazenamento_bytes: int = 0
    created_at: dt.datetime


class PorPlano(BaseModel):
    plano: str
    quantidade: int


class MetricasAdminOut(BaseModel):
    total_clientes: int
    pagantes: int  # plano efetivo != 'free'
    por_plano: list[PorPlano]
    expirando_7d: int  # licenças manuais que vencem em <= 7 dias
    expirando_30d: int  # licenças manuais que vencem em <= 30 dias
    receita_mensal_estimada: float  # Σ preco_mensal dos tenants com plano efetivo pago


class DefinirPlanoIn(BaseModel):
    """Conceder/trocar plano (manual). meses=None → sem expiração."""

    plano: str
    meses: int | None = Field(default=None, gt=0)
    observacao: str | None = None


class RenovarPlanoIn(BaseModel):
    meses: int = Field(gt=0)


class PlanoCatalogoOut(BaseModel):
    codigo: str
    nome: str
    limites: dict
    flags: dict
    preco_mensal: float | None = None
    ativo: bool
    ordem: int


class PlanoUpsertIn(BaseModel):
    nome: str
    limites: dict = Field(default_factory=dict)
    flags: dict = Field(default_factory=dict)
    preco_mensal: float | None = None
    ativo: bool = True
    ordem: int = 0
