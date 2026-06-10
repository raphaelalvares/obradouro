import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { uuidv4 } from "@/lib/uuid"

// ===================== tipos (espelham schemas/templates.py) =====================
export interface TemplateResumo {
  id: string
  tipo: string
  nivel: string
  area_referencia: number | null
  ativo: boolean
  n_itens: number
  created_at: string
  updated_at: string
}

export interface TemplateItem {
  id: string
  servico_id: string
  descricao: string
  unidade: string | null
  custo_mo: number
  custo_material: number
  custo_equipamento: number
  etapa: string | null
  por_area: boolean
  fator: number
  ordem: number
}

export interface Template {
  id: string
  tipo: string
  nivel: string
  area_referencia: number | null
  ativo: boolean
  created_at: string
  updated_at: string
  itens: TemplateItem[]
}

export interface TemplateForm {
  tipo: string
  nivel: string
  area_referencia?: number | null
  ativo?: boolean
}

export interface TemplateItemForm {
  servico_id?: string
  etapa?: string | null
  por_area?: boolean
  fator?: number
  ordem?: number
}

export interface PromoverTemplateLinha {
  descricao: string
  unidade?: string | null
  quantidade?: number | null
  valor_mo?: number
  valor_material?: number
  valor_equipamento?: number
  etapa?: string | null
}

const BASE = "/api/v1/me/templates"
const listKey = ["templates"] as const
const oneKey = (id: string) => ["template", id] as const

export function useTemplates(enabled = true) {
  return useQuery({
    queryKey: listKey,
    queryFn: () => api.get<TemplateResumo[]>(BASE),
    enabled,
  })
}

export function useTemplate(id: string | null) {
  return useQuery({
    queryKey: oneKey(id ?? ""),
    queryFn: () => api.get<Template>(`${BASE}/${id}`),
    enabled: Boolean(id),
  })
}

function useInvalidate() {
  const qc = useQueryClient()
  return (id?: string) => {
    void qc.invalidateQueries({ queryKey: listKey })
    if (id) void qc.invalidateQueries({ queryKey: oneKey(id) })
  }
}

export function useCriarTemplate() {
  const inval = useInvalidate()
  return useMutation({
    mutationFn: (form: TemplateForm) =>
      api.post<Template>(BASE, { id: uuidv4(), ...form, tipo: form.tipo.trim(), nivel: form.nivel.trim() }),
    onSuccess: (t) => inval(t.id),
  })
}

export function useAtualizarTemplate() {
  const inval = useInvalidate()
  return useMutation({
    mutationFn: (v: { id: string; patch: Partial<TemplateForm> }) =>
      api.patch<Template>(`${BASE}/${v.id}`, v.patch),
    onSuccess: (t) => inval(t.id),
  })
}

export function useExcluirTemplate() {
  const inval = useInvalidate()
  return useMutation({
    mutationFn: (id: string) => api.del<void>(`${BASE}/${id}`),
    onSuccess: () => inval(),
  })
}

export function useAddTemplateItem(templateId: string) {
  const inval = useInvalidate()
  return useMutation({
    mutationFn: (form: TemplateItemForm) =>
      api.post<Template>(`${BASE}/${templateId}/itens`, {
        id: uuidv4(),
        por_area: false,
        fator: 1,
        ordem: 0,
        ...form,
      }),
    onSuccess: (t) => inval(t.id),
  })
}

export function useEditTemplateItem(templateId: string) {
  const inval = useInvalidate()
  return useMutation({
    mutationFn: (v: { itemId: string; patch: TemplateItemForm }) =>
      api.patch<Template>(`${BASE}/${templateId}/itens/${v.itemId}`, v.patch),
    onSuccess: (t) => inval(t.id),
  })
}

export function useDelTemplateItem(templateId: string) {
  const inval = useInvalidate()
  return useMutation({
    mutationFn: (itemId: string) => api.del<Template>(`${BASE}/${templateId}/itens/${itemId}`),
    onSuccess: (t) => inval(t.id),
  })
}

export function usePromoverTemplate() {
  const qc = useQueryClient()
  const inval = useInvalidate()
  return useMutation({
    mutationFn: (data: {
      tipo: string
      nivel: string
      area_referencia?: number | null
      itens: PromoverTemplateLinha[]
    }) => api.post<Template>(`${BASE}/promover`, data),
    onSuccess: (t) => {
      inval(t.id)
      // 'promover' CRIA serviços no catálogo → atualiza a lista/selects que leem ['catalogo'].
      void qc.invalidateQueries({ queryKey: ["catalogo"] })
    },
  })
}
