import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"

export type EstadoItem = "pendente" | "em_andamento" | "concluido"

export interface Item {
  id: string
  etapa_id: string
  nome: string
  estado: EstadoItem
  concluido_por: string | null
  concluido_por_nome: string | null
  concluido_em: string | null
  ordem: number
  seq_humano: number | null
  updated_at: string
}

export interface Etapa {
  id: string
  nome: string
  ordem: number
  seq_humano: number | null
  updated_at: string
  itens: Item[]
}

export interface ChecklistTree {
  obra_id: string
  etapas: Etapa[]
}

export interface ImportResumo {
  etapas_novas: number
  etapas_existentes: number
  itens_novos: number
  itens_existentes: number
}

const treeKey = (obraId: string) => ["checklist", obraId] as const

export function useChecklist(obraId: string) {
  return useQuery({
    queryKey: treeKey(obraId),
    queryFn: () => api.get<ChecklistTree>(`/api/v1/obras/${obraId}/checklist`),
  })
}

export function useCriarEtapa(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (nome: string) =>
      api.post<Etapa>(`/api/v1/obras/${obraId}/etapas`, {
        id: crypto.randomUUID(),
        nome: nome.trim(),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

export function useCriarItem(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { etapa_id: string; nome: string }) =>
      api.post<Item>(`/api/v1/obras/${obraId}/itens`, {
        id: crypto.randomUUID(),
        etapa_id: v.etapa_id,
        nome: v.nome.trim(),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

/** Toggle de estado com UI OTIMISTA (atualiza o cache antes da resposta; reverte no erro). */
export function useToggleItem(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { item: Item; estado: EstadoItem }) =>
      api.patch<Item>(`/api/v1/obras/${obraId}/itens/${v.item.id}/estado`, {
        estado: v.estado,
        estado_de: v.item.estado, // detecção de conflito offline (servidor → 409 se base mudou)
      }),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: treeKey(obraId) })
      const prev = qc.getQueryData<ChecklistTree>(treeKey(obraId))
      if (prev) {
        qc.setQueryData<ChecklistTree>(treeKey(obraId), {
          ...prev,
          etapas: prev.etapas.map((e) => ({
            ...e,
            itens: e.itens.map((i) => (i.id === v.item.id ? { ...i, estado: v.estado } : i)),
          })),
        })
      }
      return { prev }
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(treeKey(obraId), ctx.prev)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

export function useExcluirEtapa(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (etapaId: string) =>
      api.del<{ deleted: boolean; itens_removidos: number }>(
        `/api/v1/obras/${obraId}/etapas/${etapaId}`,
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

export function useExcluirItem(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (itemId: string) => api.del(`/api/v1/obras/${obraId}/itens/${itemId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

export function useImportarChecklist(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData()
      fd.append("arquivo", file)
      return api.postForm<ImportResumo>(`/api/v1/obras/${obraId}/checklist/importar`, fd)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}
