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
  // marco de entrega (null = não entregue). Marcar expira os acessos de cliente "até a entrega".
  entregue_em: string | null
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

/** Marca/desmarca a ENTREGA da obra (marco). Marcar expira os acessos "até a entrega". Só arquiteto. */
export function useMarcarEntrega(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (entregue: boolean) =>
      entregue
        ? api.post<Obra>(`/api/v1/obras/${id}/entrega`)
        : api.del<Obra>(`/api/v1/obras/${id}/entrega`),
    onSuccess: (o) => {
      qc.setQueryData(["obra", id], o)
      void qc.invalidateQueries({ queryKey: OBRAS_KEY })
      // marcar/desmarcar entrega flipa os acessos 'até a entrega' (expirado) → atualiza a lista
      void qc.invalidateQueries({ queryKey: ["acessos-cliente", "obra", id] })
    },
  })
}
