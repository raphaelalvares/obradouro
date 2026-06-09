import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { uuidv4 } from "@/lib/uuid"

export type PapelObra = "arquiteto" | "cliente" | "prestador"

export interface Obra {
  id: string
  nome: string
  status: "ativa" | "arquivada"
  seq_humano: number | null
  created_at: string
  // janela da obra (cronograma macro)
  data_inicio: string | null
  data_fim: string | null
  // papel do usuário corrente na obra (gateia a UI). Ausente na resposta de criação.
  meu_papel: PapelObra | null
}

const OBRAS_KEY = ["obras"] as const

export function useObras() {
  return useQuery({
    queryKey: OBRAS_KEY,
    queryFn: () => api.get<Obra[]>("/api/v1/obras"),
  })
}

export function useObra(id: string) {
  return useQuery({
    queryKey: ["obra", id],
    queryFn: () => api.get<Obra>(`/api/v1/obras/${id}`),
  })
}

export function useCriarObra() {
  const qc = useQueryClient()
  return useMutation({
    // id gerado no cliente (offline/dual-ID); o backend atribui o seq_humano.
    mutationFn: (nome: string) =>
      api.post<Obra>("/api/v1/obras", { id: uuidv4(), nome: nome.trim() }),
    onSuccess: () => qc.invalidateQueries({ queryKey: OBRAS_KEY }),
  })
}

/** Define a janela da obra (início/fim do cronograma macro). Só arquiteto. */
export function useSetObraDatas(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { data_inicio: string | null; data_fim: string | null }) =>
      api.patch<Obra>(`/api/v1/obras/${id}/datas`, v),
    onSuccess: (o) => {
      qc.setQueryData(["obra", id], o)
      void qc.invalidateQueries({ queryKey: OBRAS_KEY })
    },
  })
}
