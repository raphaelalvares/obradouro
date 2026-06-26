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
  obras_ativas: number
  armazenamento_bytes: number
  created_at: string
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
  receita_mensal_estimada: number
}

export interface PlanoCatalogo {
  codigo: string
  nome: string
  limites: Record<string, number>
  flags: Record<string, boolean>
  preco_mensal: number | null
  ativo: boolean
  ordem: number
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
