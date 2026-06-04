import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"

export interface CobrancaStatus {
  configurado: boolean // backend tem Stripe configurado? (senão a UI esconde assinar/gerenciar)
  plano: string
  status: string | null // status da subscription no Stripe (active/past_due/canceled…)
  current_period_end: string | null
  tem_assinatura: boolean
}

const cobrancaKey = ["cobranca"] as const

export function useCobranca() {
  return useQuery({
    queryKey: cobrancaKey,
    queryFn: () => api.get<CobrancaStatus>("/api/v1/me/cobranca"),
  })
}

/** Inicia o checkout (assinar Pro) e redireciona p/ a página hospedada do Stripe. */
export function useAssinar() {
  return useMutation({
    mutationFn: () => api.post<{ url: string }>("/api/v1/me/cobranca/checkout"),
    onSuccess: ({ url }) => {
      window.location.href = url
    },
  })
}

/** Abre o Customer Portal do Stripe (gerenciar/cancelar) e redireciona. */
export function usePortal() {
  return useMutation({
    mutationFn: () => api.post<{ url: string }>("/api/v1/me/cobranca/portal"),
    onSuccess: ({ url }) => {
      window.location.href = url
    },
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
