import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"

/** Documento legal cuja versão vigente o usuário ainda não aceitou. Vazio = tudo em dia. */
export interface DocumentoPendente {
  documento: string
  versao: string
}

const pendentesKey = ["aceites-pendentes"] as const

/** Pendências de aceite do usuário corrente. `enabled` p/ só consultar quando há sessão. */
export function usePendentesAceite(enabled: boolean) {
  return useQuery({
    queryKey: pendentesKey,
    enabled,
    queryFn: () => api.get<DocumentoPendente[]>("/api/v1/me/aceites/pendentes"),
    staleTime: 5 * 60 * 1000,
  })
}

/** Registra a prova de aceite (versão vigente carimbada no backend) e revalida as pendências. */
export function useRegistrarAceite() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (origem: "gate") => api.post("/api/v1/me/aceites", { origem }),
    onSuccess: () => qc.invalidateQueries({ queryKey: pendentesKey }),
  })
}
