import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { uuidv4 } from "@/lib/uuid"

// ===================== tipos (espelham schemas/catalogo.py) =====================
// Custos são UNITÁRIOS (R$/unidade) — diferente do orçamento, que guarda subtotal por linha.
export interface ServicoCatalogo {
  id: string
  descricao: string
  unidade: string | null
  custo_mo: number
  custo_material: number
  custo_equipamento: number
  etapa_sugerida: string | null
  ativo: boolean
  created_at: string
  updated_at: string
}

export interface ServicoForm {
  descricao: string
  unidade?: string | null
  custo_mo?: number
  custo_material?: number
  custo_equipamento?: number
  etapa_sugerida?: string | null
  ativo?: boolean
}

/** 'Salvar no catálogo' a partir de uma linha de orçamento (subtotais + qtd → unitário no backend). */
export interface PromoverServico {
  descricao: string
  unidade?: string | null
  quantidade?: number | null
  valor_mo?: number
  valor_material?: number
  valor_equipamento?: number
  etapa_sugerida?: string | null
}

export interface ServicoPromovido extends ServicoCatalogo {
  criado: boolean
}

const BASE = "/api/v1/me/catalogo"
const catalogoKey = ["catalogo"] as const

export function useCatalogo(enabled = true) {
  return useQuery({
    queryKey: catalogoKey,
    queryFn: () => api.get<ServicoCatalogo[]>(BASE),
    enabled,
  })
}

export function useCriarServico() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (form: ServicoForm) =>
      api.post<ServicoCatalogo>(BASE, {
        id: uuidv4(),
        custo_mo: 0,
        custo_material: 0,
        custo_equipamento: 0,
        ...form,
        descricao: form.descricao.trim(),
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: catalogoKey }),
  })
}

export function useAtualizarServico() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; patch: Partial<ServicoForm> }) =>
      api.patch<ServicoCatalogo>(`${BASE}/${v.id}`, v.patch),
    onSuccess: () => void qc.invalidateQueries({ queryKey: catalogoKey }),
  })
}

export function useExcluirServico() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.del<void>(`${BASE}/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: catalogoKey }),
  })
}

export function usePromoverServico() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: PromoverServico) => api.post<ServicoPromovido>(`${BASE}/promover`, data),
    onSuccess: () => void qc.invalidateQueries({ queryKey: catalogoKey }),
  })
}
