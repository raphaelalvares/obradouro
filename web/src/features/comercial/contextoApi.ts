import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"

export type CanalPreferido = "whatsapp" | "telefone" | "email"

/** Perfil ESTRUTURADO do cliente (o que regras/automação leem). */
export interface ContextoPerfil {
  canal_preferido?: CanalPreferido | null
  melhor_horario?: string | null
  cadencia_dias?: number | null
  decisor?: string | null
  sensivel_a_preco?: boolean | null
}

export interface Contexto {
  oportunidade_id: string
  perfil: ContextoPerfil
  resumo: string | null
  existe: boolean
  atualizado_em: string | null
}

export interface ContextoForm {
  perfil: ContextoPerfil
  resumo: string | null
}

const key = (opId: string) => ["oportunidade-contexto", opId] as const

export function useContexto(opId: string, enabled = true) {
  return useQuery({
    queryKey: key(opId),
    queryFn: () => api.get<Contexto>(`/api/v1/oportunidades/${opId}/contexto`),
    enabled: enabled && Boolean(opId),
  })
}

export function useSalvarContexto(opId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: ContextoForm) => api.put<Contexto>(`/api/v1/oportunidades/${opId}/contexto`, v),
    onSuccess: (data) => qc.setQueryData(key(opId), data),
  })
}
