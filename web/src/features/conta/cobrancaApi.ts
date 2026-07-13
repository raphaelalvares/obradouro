import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"

export interface CobrancaStatus {
  configurado: boolean // backend tem Stripe configurado? (senão a UI esconde assinar/gerenciar)
  plano: string
  status: string | null // status da subscription no Stripe (active/past_due/canceled…)
  current_period_end: string | null
  tem_assinatura: boolean
  cancelamento_agendado: boolean // cancela no fim do período → "acesso até" + botão "Reativar"
  assinante_desde: string | null
  ultimo_pagamento_em: string | null
  ultimo_pagamento_cents: number | null
  fatura_pendente_url: string | null // invoice aberta (past_due) → CTA "Pagar" no banner global
}

export interface PlanoAssinavel {
  codigo: string
  nome: string
  limites: Record<string, number>
  flags: Record<string, boolean>
  preco_mensal: number | null
  ordem: number
}

// ---------------------------------------------------------------- Financeiro (add-on de storage)
export interface AddOnArmazenamento {
  base_mb: number // o que o plano dá (-1 = ilimitado)
  extra_mb: number // cortesia do admin
  contratado_mb: number // contratado via Stripe
  efetivo_mb: number // limite total em vigor (-1 = ilimitado)
  usado_bytes: number
  contratado_gb: number
  preco_gb_centavos: number // preço/GB p/ exibir (o cobrado sai do Stripe)
  mensal_cents: number // quanto o contratado custa/mês
  configuravel: boolean // add-on configurado no Stripe? (senão esconde "contratar")
}

export interface PagamentoFin {
  valor_cents: number
  moeda: string
  plano_codigo: string | null
  pago_em: string
}

export interface Financeiro {
  configurado: boolean
  plano: string
  status: string | null
  current_period_end: string | null
  tem_assinatura: boolean
  cancelamento_agendado: boolean
  assinante_desde: string | null
  pode_gerenciar: boolean
  fatura_pendente_url: string | null // invoice aberta → botão "Pagar"
  armazenamento: AddOnArmazenamento
  pagamentos: PagamentoFin[]
}

const cobrancaKey = ["cobranca"] as const
const planosAssinaveisKey = [...cobrancaKey, "planos"] as const
const financeiroKey = [...cobrancaKey, "financeiro"] as const

export function useCobranca() {
  return useQuery({
    queryKey: cobrancaKey,
    queryFn: () => api.get<CobrancaStatus>("/api/v1/me/cobranca"),
  })
}

/** Catálogo assinável (multi-plano) — monta o seletor de planos. */
export function usePlanosAssinaveis() {
  return useQuery({
    queryKey: planosAssinaveisKey,
    queryFn: () => api.get<PlanoAssinavel[]>("/api/v1/me/cobranca/planos"),
  })
}

/** Inicia o checkout (assinar/trocar plano) e redireciona p/ a página hospedada do Stripe. Aceita o
 * código do plano (string) ou { plano, winback } — winback aplica o cupom de retorno (se elegível). */
export function useAssinar() {
  return useMutation({
    mutationFn: (arg?: string | { plano?: string; winback?: boolean }) => {
      const o = typeof arg === "string" ? { plano: arg } : (arg ?? {})
      return api.post<{ url: string }>("/api/v1/me/cobranca/checkout", {
        plano: o.plano ?? null,
        winback: o.winback ?? false,
      })
    },
    onSuccess: ({ url }) => {
      window.location.href = url
    },
  })
}

/** Abre o Customer Portal do Stripe (gerenciar/cancelar/renovar/trocar cartão) e redireciona. */
export function usePortal() {
  return useMutation({
    mutationFn: () => api.post<{ url: string }>("/api/v1/me/cobranca/portal"),
    onSuccess: ({ url }) => {
      window.location.href = url
    },
  })
}

/** Cancela a assinatura no fim do período pago (mantém o acesso até lá). */
export function useCancelarAssinatura() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<CobrancaStatus>("/api/v1/me/cobranca/cancelar"),
    onSuccess: (status) => qc.setQueryData(cobrancaKey, status),
  })
}

/** Desfaz o cancelamento agendado (volta a renovar). */
export function useReativarAssinatura() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<CobrancaStatus>("/api/v1/me/cobranca/reativar"),
    onSuccess: (status) => qc.setQueryData(cobrancaKey, status),
  })
}

/** Invalida plano/cobrança (ex.: ao voltar do checkout com ?cobranca=sucesso). */
export function useInvalidarCobranca() {
  const qc = useQueryClient()
  return () => {
    void qc.invalidateQueries({ queryKey: cobrancaKey })
    void qc.invalidateQueries({ queryKey: ["quota"] })
  }
}

/** Área de Financeiro do assinante: plano + add-on de armazenamento + faturas. */
export function useFinanceiro() {
  return useQuery({
    queryKey: financeiroKey,
    queryFn: () => api.get<Financeiro>("/api/v1/me/financeiro"),
  })
}

/** Contrata/ajusta/cancela o add-on de armazenamento (gb_total = total, não delta; 0 cancela). */
export function useContratarArmazenamento() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (gb_total: number) =>
      api.post<Financeiro>("/api/v1/me/armazenamento/contratar", { gb_total }),
    onSuccess: (fin) => {
      qc.setQueryData(financeiroKey, fin)
      void qc.invalidateQueries({ queryKey: cobrancaKey }) // revalida status + financeiro
      void qc.invalidateQueries({ queryKey: ["quota"] }) // o limite mudou
    },
  })
}
