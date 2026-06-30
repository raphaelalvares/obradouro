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
}

export interface PlanoAssinavel {
  codigo: string
  nome: string
  limites: Record<string, number>
  flags: Record<string, boolean>
  preco_mensal: number | null
  ordem: number
}

const cobrancaKey = ["cobranca"] as const
const planosAssinaveisKey = [...cobrancaKey, "planos"] as const

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

/** Inicia o checkout (assinar/trocar plano) e redireciona p/ a página hospedada do Stripe. */
export function useAssinar() {
  return useMutation({
    mutationFn: (plano?: string) =>
      api.post<{ url: string }>("/api/v1/me/cobranca/checkout", { plano: plano ?? null }),
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
