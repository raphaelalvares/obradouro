import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { uuidv4 } from "@/lib/uuid"

// ===================== tipos (espelham schemas/funcoes.py) =====================
// Função/cargo = biblioteca REUTILIZÁVEL no tenant (entre obras). Usada no efetivo do diário.
export interface Funcao {
  id: string
  nome: string
  ativo: boolean
  created_at: string
  updated_at: string
}

export interface FuncaoForm {
  nome: string
  ativo?: boolean
}

/** Picker do diário (GET /obras/{id}/funcoes): só funções ativas do dono da obra. */
export interface FuncaoSimples {
  id: string
  nome: string
}

const BASE = "/api/v1/me/funcoes"
const funcoesKey = ["funcoes"] as const
const funcoesObraKey = (obraId: string) => ["funcoes-obra", obraId] as const

export function useFuncoes(enabled = true) {
  return useQuery({
    queryKey: funcoesKey,
    queryFn: () => api.get<Funcao[]>(BASE),
    enabled,
  })
}

/** Picker por obra (funciona p/ arquiteto E prestador via função SECURITY DEFINER no backend). */
export function useFuncoesObra(obraId: string, enabled = true) {
  return useQuery({
    queryKey: funcoesObraKey(obraId),
    queryFn: () => api.get<FuncaoSimples[]>(`/api/v1/obras/${obraId}/funcoes`),
    enabled: enabled && Boolean(obraId),
  })
}

export function useCriarFuncao() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (form: FuncaoForm) =>
      api.post<Funcao>(BASE, { id: uuidv4(), ...form, nome: form.nome.trim() }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: funcoesKey })
      void qc.invalidateQueries({ queryKey: ["funcoes-obra"] }) // os pickers abertos refrescam
    },
  })
}

export function useAtualizarFuncao() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; patch: Partial<FuncaoForm> }) =>
      api.patch<Funcao>(`${BASE}/${v.id}`, v.patch),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: funcoesKey })
      void qc.invalidateQueries({ queryKey: ["funcoes-obra"] })
    },
  })
}

export function useExcluirFuncao() {
  const qc = useQueryClient()
  return useMutation({
    // sem FK p/ o diário (o nome do efetivo é snapshot) → não invalida 'diario'; só a lib + pickers.
    mutationFn: (id: string) => api.del<void>(`${BASE}/${id}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: funcoesKey })
      void qc.invalidateQueries({ queryKey: ["funcoes-obra"] })
    },
  })
}
