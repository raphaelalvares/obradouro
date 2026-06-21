import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"

// ===================== tipos (espelham schemas/acompanhamento.py) =====================
/** Medição do avanço de UMA tarefa numa entrada do diário (SNAPSHOT datado pela data do diário). */
export interface DiarioTarefa {
  id: string
  item_id: string
  item_nome: string
  item_seq: number | null
  etapa_nome: string | null
  progresso_pct: number // avanço gravado (0..100)
  qtd_executada: number | null
  unidade: string | null // do item (p/ exibir "30 de 100 m²")
  quantidade: number | null // total planejado do item
  observacao: string | null
  created_by: string | null
  n_fotos: number
  created_at: string
  updated_at: string
}

/** Payload do upsert: id gerado no cliente + tarefa + avanço (% direto OU quantidade executada). */
export interface DiarioTarefaForm {
  id: string
  item_id: string
  progresso_pct?: number | null
  qtd_executada?: number | null
  observacao?: string | null
}

const key = (obraId: string, diarioId: string) => ["diario-tarefas", obraId, diarioId] as const

export function useDiarioTarefas(obraId: string, diarioId: string, enabled = true) {
  return useQuery({
    queryKey: key(obraId, diarioId),
    queryFn: () => api.get<DiarioTarefa[]>(`/api/v1/obras/${obraId}/diario/${diarioId}/tarefas`),
    enabled: enabled && Boolean(obraId && diarioId),
  })
}

/** invalida a lista de medições do diário E o que depende do progresso (checklist + curva-S). */
function invalidar(qc: ReturnType<typeof useQueryClient>, obraId: string, diarioId: string) {
  void qc.invalidateQueries({ queryKey: key(obraId, diarioId) })
  void qc.invalidateQueries({ queryKey: ["checklist", obraId] })
  void qc.invalidateQueries({ queryKey: ["avanco", obraId] })
}

// O diarioId vai por CHAMADA (não no hook): na criação o RDO só nasce ao vincular a 1ª tarefa, então
// o id não existe no render que monta o hook — passá-lo no mutate evita closure obsoleta.
export function useDefinirDiarioTarefa(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ diarioId, ...form }: DiarioTarefaForm & { diarioId: string }) =>
      api.put<DiarioTarefa>(`/api/v1/obras/${obraId}/diario/${diarioId}/tarefas`, form),
    onSuccess: (_d, v) => invalidar(qc, obraId, v.diarioId),
  })
}

export function useExcluirDiarioTarefa(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ diarioId, dtId }: { diarioId: string; dtId: string }) =>
      api.del(`/api/v1/obras/${obraId}/diario/${diarioId}/tarefas/${dtId}`),
    onSuccess: (_d, v) => invalidar(qc, obraId, v.diarioId),
  })
}
