import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"

// ---------------------------------------------------------------- tipos (espelham schemas/admin.py)
export interface TenantAdmin {
  tenant_id: string
  email: string
  nome: string | null
  nome_escritorio: string | null
  plano_codigo: string // plano EFETIVO (respeita expiração)
  plano_nome: string
  origem: string | null // 'manual' | 'stripe' | null
  expira_em: string | null // validade da concessão manual (null = sem expiração)
  observacao: string | null
  cobranca_status: string | null // status da subscription no Stripe
  current_period_end: string | null
  assinante_desde: string | null // 1ª época paga (histórico)
  ultimo_pagamento_em: string | null
  ultimo_pagamento_cents: number | null
  obras_ativas: number
  armazenamento_bytes: number
  created_at: string // "cliente desde" (cadastro)
}

export interface PorPlano {
  plano: string
  quantidade: number
}

export interface MetricasAdmin {
  total_clientes: number
  pagantes: number
  por_plano: PorPlano[]
  expirando_7d: number
  expirando_30d: number
  receita_mensal_estimada: number // MRR estimado
  novos_mes: number
  churn_30d: number
}

export interface HistoricoPlano {
  plano_codigo: string
  origem: string
  inicio: string
  fim: string | null // null = vigente
  motivo: string | null
}

export interface Pagamento {
  valor_cents: number
  moeda: string
  plano_codigo: string | null
  pago_em: string
}

export interface TenantHistorico {
  historico: HistoricoPlano[]
  pagamentos: Pagamento[]
}

export interface AcessoClienteAdmin {
  id: string
  email: string
  estado: string
  cadastrado: boolean
  projeto_id: string | null
  obra_id: string | null
  alvo_nome: string | null
  created_at: string
}

export interface AlvoAdmin {
  id: string
  nome: string
  tipo: "projeto" | "obra"
  obra_id: string | null
}

export interface AcessosAdmin {
  acessos: AcessoClienteAdmin[]
  alvos: AlvoAdmin[]
}

export interface SuporteStatus {
  email: string | null
  email_confirmado: boolean
  banido: boolean
}

export interface Nota {
  id: string
  texto: string
  autor_email: string | null
  created_at: string
}

export interface AuditLog {
  id: string
  acao: string
  detalhe: Record<string, unknown>
  created_at: string
  admin_email: string | null
  tenant_alvo: string | null
  tenant_email: string | null
}

export interface PlanoCatalogo {
  codigo: string
  nome: string
  limites: Record<string, number>
  flags: Record<string, boolean>
  preco_mensal: number | null
  ativo: boolean
  ordem: number
  stripe_price_id: string | null // sem ele o plano não é assinável (multi-plano)
}

export interface DefinirPlanoBody {
  plano: string
  meses: number | null
  observacao: string | null
}

// ---------------------------------------------------------------- hooks
const adminKey = ["admin"] as const
const tenantsKey = [...adminKey, "tenants"] as const
const metricasKey = [...adminKey, "metricas"] as const
const planosKey = [...adminKey, "planos"] as const

/** É admin da plataforma? Cacheado por sessão (gateia o menu/rota sem refazer a cada navegação). */
export function useIsAdmin() {
  return useQuery({
    queryKey: [...adminKey, "me"],
    queryFn: () => api.get<{ is_admin: boolean }>("/api/v1/admin/me"),
    staleTime: Infinity,
  })
}

export function useAdminTenants() {
  return useQuery({
    queryKey: tenantsKey,
    queryFn: () => api.get<TenantAdmin[]>("/api/v1/admin/tenants"),
  })
}

export function useAdminMetricas() {
  return useQuery({
    queryKey: metricasKey,
    queryFn: () => api.get<MetricasAdmin>("/api/v1/admin/metricas"),
  })
}

export function useAdminPlanos() {
  return useQuery({
    queryKey: planosKey,
    queryFn: () => api.get<PlanoCatalogo[]>("/api/v1/admin/planos"),
  })
}

/** Detalhe de billing de um cliente: timeline de planos + pagamentos. */
export function useTenantHistorico(tenantId: string | null) {
  return useQuery({
    queryKey: [...tenantsKey, tenantId, "historico"],
    queryFn: () => api.get<TenantHistorico>(`/api/v1/admin/tenants/${tenantId}/historico`),
    enabled: !!tenantId,
  })
}

// ---------------------------------------------------------------- notificação de novo cadastro
const novosKey = [...adminKey, "novos"] as const

/** Quantos cadastros novos desde a última visita (badge). Só busca quando `enabled` (é admin). */
export function useNovosClientes(enabled: boolean) {
  return useQuery({
    queryKey: novosKey,
    queryFn: () => api.get<{ novos: number }>("/api/v1/admin/novos"),
    enabled,
    staleTime: 60_000,
  })
}

export function useMarcarVistos() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<void>("/api/v1/admin/novos/visto"),
    onSuccess: () => void qc.invalidateQueries({ queryKey: novosKey }),
  })
}

// ---------------------------------------------------------------- auditoria
export function useAuditLog() {
  return useQuery({
    queryKey: [...adminKey, "log"],
    queryFn: () => api.get<AuditLog[]>("/api/v1/admin/log"),
  })
}

// ---------------------------------------------------------------- acessos de cliente nas obras
export function useAdminAcessos(tenantId: string | null) {
  return useQuery({
    queryKey: [...tenantsKey, tenantId, "acessos"],
    queryFn: () => api.get<AcessosAdmin>(`/api/v1/admin/tenants/${tenantId}/acessos`),
    enabled: !!tenantId,
  })
}

export function useAutorizarAcesso(tenantId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { projeto_id: string | null; obra_id: string | null; email: string }) =>
      api.post<void>(`/api/v1/admin/tenants/${tenantId}/acessos`, body),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: [...tenantsKey, tenantId, "acessos"] }),
  })
}

export function useRevogarAcesso(tenantId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (acessoId: string) => api.del<void>(`/api/v1/admin/acessos/${acessoId}`),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: [...tenantsKey, tenantId, "acessos"] }),
  })
}

// ---------------------------------------------------------------- suporte (GoTrue)
export function useSuporteStatus(tenantId: string | null) {
  return useQuery({
    queryKey: [...tenantsKey, tenantId, "suporte"],
    queryFn: () => api.get<SuporteStatus>(`/api/v1/admin/tenants/${tenantId}/suporte`),
    enabled: !!tenantId,
    retry: false,
  })
}

export function useSuporteAcao(tenantId: string) {
  const qc = useQueryClient()
  const invalidar = () =>
    void qc.invalidateQueries({ queryKey: [...tenantsKey, tenantId, "suporte"] })
  const reenviar = useMutation({
    mutationFn: () =>
      api.post<void>(`/api/v1/admin/tenants/${tenantId}/suporte/reenviar-confirmacao`),
  })
  const resetSenha = useMutation({
    mutationFn: () =>
      api.post<{ link: string }>(`/api/v1/admin/tenants/${tenantId}/suporte/reset-senha`),
  })
  const suspender = useMutation({
    mutationFn: () => api.post<void>(`/api/v1/admin/tenants/${tenantId}/suporte/suspender`),
    onSuccess: invalidar,
  })
  const reativar = useMutation({
    mutationFn: () => api.post<void>(`/api/v1/admin/tenants/${tenantId}/suporte/reativar`),
    onSuccess: invalidar,
  })
  return { reenviar, resetSenha, suspender, reativar }
}

// ---------------------------------------------------------------- notas internas
export function useNotas(tenantId: string | null) {
  return useQuery({
    queryKey: [...tenantsKey, tenantId, "notas"],
    queryFn: () => api.get<Nota[]>(`/api/v1/admin/tenants/${tenantId}/notas`),
    enabled: !!tenantId,
  })
}

export function useCriarNota(tenantId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (texto: string) =>
      api.post<void>(`/api/v1/admin/tenants/${tenantId}/notas`, { texto }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [...tenantsKey, tenantId, "notas"] }),
  })
}

export function useExcluirNota(tenantId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (notaId: string) => api.del<void>(`/api/v1/admin/notas/${notaId}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [...tenantsKey, tenantId, "notas"] }),
  })
}

function useInvalidarTenants() {
  const qc = useQueryClient()
  return () => {
    void qc.invalidateQueries({ queryKey: tenantsKey })
    void qc.invalidateQueries({ queryKey: metricasKey })
  }
}

/** Conceder/trocar plano (manual). meses=null → sem expiração. */
export function useDefinirPlano() {
  const invalidar = useInvalidarTenants()
  return useMutation({
    mutationFn: ({ tenantId, body }: { tenantId: string; body: DefinirPlanoBody }) =>
      api.post<void>(`/api/v1/admin/tenants/${tenantId}/plano`, body),
    onSuccess: invalidar,
  })
}

/** Renovar +N meses (mantém o plano). */
export function useRenovarPlano() {
  const invalidar = useInvalidarTenants()
  return useMutation({
    mutationFn: ({ tenantId, meses }: { tenantId: string; meses: number }) =>
      api.post<void>(`/api/v1/admin/tenants/${tenantId}/renovar`, { meses }),
    onSuccess: invalidar,
  })
}

/** Revogar (volta a free imediatamente). */
export function useRevogarPlano() {
  const invalidar = useInvalidarTenants()
  return useMutation({
    mutationFn: (tenantId: string) => api.del<void>(`/api/v1/admin/tenants/${tenantId}/plano`),
    onSuccess: invalidar,
  })
}

/** Criar/editar plano do catálogo. */
export function useUpsertPlano() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ codigo, body }: { codigo: string; body: Omit<PlanoCatalogo, "codigo"> }) =>
      api.put<void>(`/api/v1/admin/planos/${codigo}`, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: planosKey })
      void qc.invalidateQueries({ queryKey: tenantsKey })
      void qc.invalidateQueries({ queryKey: metricasKey })
    },
  })
}

// ---------------------------------------------------------------- helpers de UI (derivações)
/** Data-fim relevante do tenant: manual usa expira_em; Stripe usa current_period_end. */
export function fimVigencia(t: TenantAdmin): string | null {
  return t.origem === "stripe" ? t.current_period_end : t.expira_em
}

/** Dias restantes até o fim da vigência (null = sem expiração / sem data). Pode ser negativo. */
export function diasRestantes(t: TenantAdmin, agora = new Date()): number | null {
  const fim = fimVigencia(t)
  if (!fim) return null
  return Math.ceil((new Date(fim).getTime() - agora.getTime()) / 86_400_000)
}

/** Tenant é pagante? (plano efetivo != free). */
export function ehPagante(t: TenantAdmin): boolean {
  return t.plano_codigo !== "free"
}
