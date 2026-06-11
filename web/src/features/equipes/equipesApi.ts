import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { uuidv4 } from "@/lib/uuid"

// ===================== tipos (espelham schemas/equipes.py) =====================
// Equipe = biblioteca REUTILIZÁVEL no tenant (entre obras). `cor` (#RRGGBB) pinta o Gantt.
export interface Equipe {
  id: string
  nome: string
  cor: string
  contato: string | null
  ativo: boolean
  created_at: string
  updated_at: string
}

export interface EquipeForm {
  nome: string
  cor?: string
  contato?: string | null
  ativo?: boolean
}

/** Paleta poka-yoke (legível no tema escuro). A 1ª (âmbar da marca) é o padrão do backend. */
export const PALETA_EQUIPES = [
  "#D8A53A", // âmbar (marca)
  "#5FB87A", // verde
  "#E5654B", // coral
  "#5B8DEF", // azul
  "#A78BFA", // roxo
  "#EC4899", // rosa
  "#22B8CF", // ciano
  "#F59E0B", // laranja
  "#84CC16", // lima
  "#94A3B8", // cinza
] as const

const BASE = "/api/v1/me/equipes"
const equipesKey = ["equipes"] as const

export function useEquipes(enabled = true) {
  return useQuery({
    queryKey: equipesKey,
    queryFn: () => api.get<Equipe[]>(BASE),
    enabled,
  })
}

export function useCriarEquipe() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (form: EquipeForm) =>
      api.post<Equipe>(BASE, {
        id: uuidv4(),
        cor: PALETA_EQUIPES[0],
        ...form,
        nome: form.nome.trim(),
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: equipesKey }),
  })
}

export function useAtualizarEquipe() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; patch: Partial<EquipeForm> }) =>
      api.patch<Equipe>(`${BASE}/${v.id}`, v.patch),
    onSuccess: () => void qc.invalidateQueries({ queryKey: equipesKey }),
  })
}

export function useExcluirEquipe() {
  const qc = useQueryClient()
  return useMutation({
    // ao excluir a equipe, o backend desliga `equipe_id` das tarefas (FK set null) → a árvore de
    // qualquer obra aberta precisa refazer p/ refletir. Invalida 'checklist' por garantia.
    mutationFn: (id: string) => api.del<void>(`${BASE}/${id}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: equipesKey })
      void qc.invalidateQueries({ queryKey: ["checklist"] })
    },
  })
}
