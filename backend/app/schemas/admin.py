"""Schemas do painel de admin da plataforma (dono do SaaS)."""

import datetime as dt
import uuid

from pydantic import BaseModel, EmailStr, Field


class AdminMeOut(BaseModel):
    is_admin: bool  # usado pelo front p/ mostrar/esconder o menu Admin (gateia a UI)


class TenantAdminOut(BaseModel):
    """Espelha admin_listar_tenants(). Um 'cliente' do SaaS = uma row de profiles (arquiteto)."""

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
    assinante_desde: dt.datetime | None = None  # 1ª época com plano != free (histórico)
    ultimo_pagamento_em: dt.datetime | None = None
    ultimo_pagamento_cents: int | None = None
    obras_ativas: int = 0
    armazenamento_bytes: int = 0  # consumo CONTABILIZADO (o que a cota cobra; sem miniaturas)
    created_at: dt.datetime  # "cliente desde" (cadastro)
    ultimo_login: dt.datetime | None = None  # auth.users.last_sign_in_at (último login)
    ultima_atividade_em: dt.datetime | None = None  # última ação no app (profiles)
    armazenamento_limite_mb: int = 0  # limite EFETIVO (plano + extra); -1 = ilimitado
    armazenamento_extra_mb: int = 0  # extra alocado pelo admin (0 = sem alocação)


class PorPlano(BaseModel):
    plano: str
    quantidade: int


class MetricasAdminOut(BaseModel):
    total_clientes: int
    pagantes: int  # plano efetivo != 'free'
    por_plano: list[PorPlano]
    expirando_7d: int  # licenças manuais que vencem em <= 7 dias
    expirando_30d: int  # licenças manuais que vencem em <= 30 dias
    receita_mensal_estimada: float  # MRR estimado: Σ preco_mensal dos tenants com plano pago
    novos_mes: int  # arquitetos cadastrados no mês corrente
    churn_30d: int  # tenants que caíram de pago → free nos últimos 30 dias


class HistoricoPlanoOut(BaseModel):
    plano_codigo: str
    origem: str
    inicio: dt.datetime
    fim: dt.datetime | None = None  # None = período vigente
    motivo: str | None = None


class PagamentoOut(BaseModel):
    valor_cents: int
    moeda: str
    plano_codigo: str | None = None
    pago_em: dt.datetime


class TenantHistoricoOut(BaseModel):
    """Detalhe de billing do cliente: timeline de planos + pagamentos."""

    historico: list[HistoricoPlanoOut]
    pagamentos: list[PagamentoOut]


class DefinirPlanoIn(BaseModel):
    """Conceder/trocar plano (manual). meses=None → sem expiração."""

    plano: str
    meses: int | None = Field(default=None, gt=0)
    observacao: str | None = None


class RenovarPlanoIn(BaseModel):
    meses: int = Field(gt=0)


class ArmazenamentoResumoOut(BaseModel):
    """Pool de storage p/ o painel admin. Físico (real da conta/Drive) vs cotas (contabilizado +
    comprometido). Campos físicos None quando o backend não sabe medir a conta (ex.: local)."""

    backend: str
    conta_disponivel: bool  # o backend reportou a conta? (Drive sim; local não)
    total_bytes: int | None = None  # teto físico (5 TB reais ou STORAGE_POOL_MB)
    usado_real_bytes: int | None = None  # usage — tudo na conta (Drive + Gmail + Fotos)
    usado_drive_bytes: int | None = None  # usageInDrive — só o Drive
    lixeira_bytes: int | None = None  # usageInDriveTrash — lixeira (ainda ocupa a cota)
    consumo_contabilizado_bytes: int  # Σ do que a cota cobra (sem miniaturas)
    comprometido_mb: int  # Σ dos limites efetivos (a RESERVA)
    comprometido_pagantes_mb: int  # idem, só pagantes
    n_clientes: int
    ilimitado_presente: bool  # algum cliente com storage ilimitado (não entra na soma)
    livre_para_alocar_bytes: int | None = None  # total físico − comprometido
    overcommit: bool  # comprometeu mais do que cabe fisicamente


class DefinirArmazenamentoIn(BaseModel):
    """Alocar espaço extra (MB) p/ um cliente. Negativo reduz abaixo do plano; 0 tira a alocação."""

    extra_mb: int


class ArmazenamentoMedidoOut(BaseModel):
    """Uso REAL medido no backend (varre pastas/subpastas do cliente). None = não sabe medir."""

    usado_real_bytes: int | None = None


class PlanoCatalogoOut(BaseModel):
    codigo: str
    nome: str
    limites: dict
    flags: dict
    preco_mensal: float | None = None
    ativo: bool
    ordem: int
    stripe_price_id: str | None = None  # Stripe Price; sem ele o plano não é assinável


class PlanoUpsertIn(BaseModel):
    nome: str
    limites: dict = Field(default_factory=dict)
    flags: dict = Field(default_factory=dict)
    preco_mensal: float | None = None
    ativo: bool = True
    ordem: int = 0
    stripe_price_id: str | None = None


# ----------------------------------------------------------------- gestão de e-mails de cliente
class AcessoClienteAdminOut(BaseModel):
    id: uuid.UUID
    email: str
    estado: str  # 'pendente' | 'ativo'
    cadastrado: bool  # já entrou (profile vinculado)
    projeto_id: uuid.UUID | None = None
    obra_id: uuid.UUID | None = None
    alvo_nome: str | None = None  # nome do projeto/obra
    created_at: dt.datetime


class AlvoAdminOut(BaseModel):
    id: uuid.UUID
    nome: str
    tipo: str  # 'projeto' | 'obra'
    obra_id: uuid.UUID | None = None


class AcessosAdminOut(BaseModel):
    acessos: list[AcessoClienteAdminOut]
    alvos: list[AlvoAdminOut]  # alvos disponíveis p/ convidar


class AutorizarAcessoIn(BaseModel):
    projeto_id: uuid.UUID | None = None
    obra_id: uuid.UUID | None = None
    email: EmailStr


# ----------------------------------------------------------------- suporte ao usuário (GoTrue)
class SuporteStatusOut(BaseModel):
    email: str | None = None
    email_confirmado: bool = False
    banido: bool = False


class ResetLinkOut(BaseModel):
    link: str


# ----------------------------------------------------------------- notas internas
class NotaOut(BaseModel):
    id: uuid.UUID
    texto: str
    autor_email: str | None = None
    created_at: dt.datetime


class NotaCriarIn(BaseModel):
    texto: str


# ----------------------------------------------------------------- auditoria / notificação
class AuditLogOut(BaseModel):
    id: uuid.UUID
    acao: str
    detalhe: dict
    created_at: dt.datetime
    admin_email: str | None = None
    tenant_alvo: uuid.UUID | None = None
    tenant_email: str | None = None


class NovosOut(BaseModel):
    novos: int
