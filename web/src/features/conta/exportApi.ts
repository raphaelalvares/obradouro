import { useMutation, useQuery, useQueryClient, type Query } from "@tanstack/react-query"

import { api } from "@/lib/api"

export type ExportStatus = "pendente" | "processando" | "pronto" | "erro" | "expirado"

export interface ExportJob {
  id: string
  status: ExportStatus
  tamanho_bytes: number | null
  erro: string | null
  pronto_em: string | null
  expira_em: string | null
  created_at: string
}

const exportsKey = ["exports"] as const

export function useExports() {
  return useQuery({
    queryKey: exportsKey,
    queryFn: () => api.get<ExportJob[]>("/api/v1/me/exports"),
    // enquanto houver job rodando, repesca a cada 2,5s p/ acompanhar o progresso
    refetchInterval: (q: Query<ExportJob[]>) =>
      (q.state.data ?? []).some((j) => j.status === "pendente" || j.status === "processando")
        ? 2500
        : false,
  })
}

export function useSolicitarExport() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<ExportJob>("/api/v1/me/exports"),
    onSuccess: () => void qc.invalidateQueries({ queryKey: exportsKey }),
  })
}

/** Baixa o .zip (API-only: blob autenticado → download). */
export async function baixarExport(jobId: string) {
  const blob = await api.getBlob(`/api/v1/me/exports/${jobId}/download`)
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `cria-dados-${jobId.slice(0, 8)}.zip`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}
