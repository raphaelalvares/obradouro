import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { uuidv4 } from "@/lib/uuid"

export type EstadoItem = "pendente" | "em_andamento" | "concluido"

export interface Item {
  id: string
  etapa_id: string
  parent_item_id: string | null
  nome: string
  estado: EstadoItem
  concluido_por: string | null
  concluido_por_nome: string | null
  concluido_em: string | null
  ordem: number
  seq_humano: number | null
  updated_at: string
  // cronograma (dias corridos, sem hora) — "YYYY-MM-DD"
  data_inicio: string | null
  data_fim: string | null
  duracao_dias: number | null
  // dependências (só nas tarefas top-level): bloqueada = tem predecessor não-concluído;
  // aguarda = seq_humano dos predecessores que faltam concluir.
  bloqueada: boolean
  aguarda: number[]
  // cômodo (agrupamento) + orçamento (vindos do import ou editados à mão)
  ambiente: string | null
  unidade: string | null
  quantidade: number | null
  custo_mao_obra: number | null
  custo_material: number | null
  custo_total: number | null
  // sub-itens (filhos manuais) — só vêm preenchidos nas tarefas top-level
  subitens: Item[]
}

export type DepTipo = "FS" | "SS" | "FF" | "SF"

export interface Dependencia {
  id: string
  predecessora_id: string
  sucessora_id: string
  tipo: DepTipo
  lag_dias: number
}

/** Campos editáveis de cômodo/orçamento (PATCH parcial). */
export interface ItemDetalhes {
  ambiente: string | null
  unidade: string | null
  quantidade: number | null
  custo_mao_obra: number | null
  custo_material: number | null
  custo_total: number | null
}

export interface Etapa {
  id: string
  nome: string
  ordem: number
  seq_humano: number | null
  updated_at: string
  // datas EFETIVAS: min/max das datas dos itens; se sem_itens, são as datas próprias da etapa.
  data_inicio: string | null
  data_fim: string | null
  sem_itens: boolean
  // conclusão manual da etapa (marco): só relevante p/ etapas sem tarefas. Alimenta o Gantt.
  concluida: boolean
  concluida_em: string | null
  itens: Item[]
}

export interface CronogramaEntrada {
  tipo: "item" | "etapa"
  id: string
  data_inicio: string | null
  data_fim: string | null
}

export interface ChecklistTree {
  obra_id: string
  etapas: Etapa[]
  dependencias: Dependencia[]
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
        id: uuidv4(),
        nome: nome.trim(),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

export function useCriarItem(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    // id gerado no cliente (offline) → usado tanto no POST quanto na inserção OTIMISTA do cache.
    // parent_item_id setado = SUB-ITEM da tarefa; ausente = tarefa top-level da etapa.
    mutationFn: (v: { id: string; etapa_id: string; nome: string; parent_item_id?: string }) =>
      api.post<Item>(`/api/v1/obras/${obraId}/itens`, {
        id: v.id,
        etapa_id: v.etapa_id,
        parent_item_id: v.parent_item_id ?? null,
        nome: v.nome.trim(),
      }),
    // UI OTIMISTA: aparece na hora; reverte no erro; reconcilia no fim (sem esperar a rede).
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: treeKey(obraId) })
      const prev = qc.getQueryData<ChecklistTree>(treeKey(obraId))
      const novo: Item = {
        id: v.id,
        etapa_id: v.etapa_id,
        parent_item_id: v.parent_item_id ?? null,
        nome: v.nome.trim(),
        estado: "pendente",
        concluido_por: null,
        concluido_por_nome: null,
        concluido_em: null,
        ordem: 9999,
        seq_humano: null,
        updated_at: new Date().toISOString(),
        data_inicio: null,
        data_fim: null,
        duracao_dias: null,
        bloqueada: false,
        aguarda: [],
        ambiente: null,
        unidade: null,
        quantidade: null,
        custo_mao_obra: null,
        custo_material: null,
        custo_total: null,
        subitens: [],
      }
      if (prev) {
        qc.setQueryData<ChecklistTree>(treeKey(obraId), {
          ...prev,
          etapas: prev.etapas.map((e) => {
            if (e.id !== v.etapa_id) return e
            if (v.parent_item_id) {
              return {
                ...e,
                itens: e.itens.map((t) =>
                  t.id === v.parent_item_id ? { ...t, subitens: [...t.subitens, novo] } : t,
                ),
              }
            }
            return { ...e, itens: [...e.itens, novo] }
          }),
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
        const patch = (i: Item): Item => ({
          ...(i.id === v.item.id ? { ...i, estado: v.estado } : i),
          subitens: i.subitens.map((s) =>
            s.id === v.item.id ? { ...s, estado: v.estado } : s,
          ),
        })
        qc.setQueryData<ChecklistTree>(treeKey(obraId), {
          ...prev,
          etapas: prev.etapas.map((e) => ({ ...e, itens: e.itens.map(patch) })),
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

/** Edita cômodo/orçamento do item (só arquiteto). PATCH parcial: envia só o que mudou. */
export function useAtualizarDetalhes(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { itemId: string; patch: Partial<ItemDetalhes> }) =>
      api.patch<Item>(`/api/v1/obras/${obraId}/itens/${v.itemId}/detalhes`, v.patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

/** Define início/fim de UMA tarefa (item). Só arquiteto. */
export function useSetItemDatas(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { itemId: string; data_inicio: string | null; data_fim: string | null }) =>
      api.patch<Item>(`/api/v1/obras/${obraId}/itens/${v.itemId}/datas`, {
        data_inicio: v.data_inicio,
        data_fim: v.data_fim,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

/** Define início/fim direto na ETAPA (usada quando a etapa não tem itens). Só arquiteto. */
export function useSetEtapaDatas(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { etapaId: string; data_inicio: string | null; data_fim: string | null }) =>
      api.patch<Etapa>(`/api/v1/obras/${obraId}/etapas/${v.etapaId}/datas`, {
        data_inicio: v.data_inicio,
        data_fim: v.data_fim,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

/** Marca/desmarca a ETAPA como concluída (marco; etapas sem tarefas). Só arquiteto. UI otimista. */
export function useSetEtapaConcluida(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { etapa: Etapa; concluida: boolean }) =>
      api.patch<Etapa>(`/api/v1/obras/${obraId}/etapas/${v.etapa.id}/concluida`, {
        concluida: v.concluida,
        concluida_de: v.etapa.concluida, // conflito offline (servidor → 409 se base mudou)
      }),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: treeKey(obraId) })
      const prev = qc.getQueryData<ChecklistTree>(treeKey(obraId))
      if (prev) {
        qc.setQueryData<ChecklistTree>(treeKey(obraId), {
          ...prev,
          etapas: prev.etapas.map((e) =>
            e.id === v.etapa.id ? { ...e, concluida: v.concluida } : e,
          ),
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

/** Aplica o cronograma macro (prévia editada) em lote + a janela da obra. */
export function useAplicarCronograma(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: {
      obra_data_inicio: string | null
      obra_data_fim: string | null
      entradas: CronogramaEntrada[]
    }) => api.post<ChecklistTree>(`/api/v1/obras/${obraId}/cronograma`, v),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: treeKey(obraId) })
      void qc.invalidateQueries({ queryKey: ["obra", obraId] })
    },
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

// ===================== dependências / cronograma automático (Fatia B) =====================

/** Cria uma dependência (predecessora → sucessora). Só arquiteto. */
export function useAddDep(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: {
      predecessora_id: string
      sucessora_id: string
      tipo?: DepTipo
      lag_dias?: number
    }) =>
      api.post<Dependencia>(`/api/v1/obras/${obraId}/dependencias`, {
        id: uuidv4(),
        predecessora_id: v.predecessora_id,
        sucessora_id: v.sucessora_id,
        tipo: v.tipo ?? "FS",
        lag_dias: v.lag_dias ?? 0,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

/** Atualiza tipo/folga de uma dependência. Só arquiteto. */
export function useAtualizarDep(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { depId: string; tipo?: DepTipo; lag_dias?: number }) =>
      api.patch<Dependencia>(`/api/v1/obras/${obraId}/dependencias/${v.depId}`, {
        tipo: v.tipo,
        lag_dias: v.lag_dias,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

/** Exclui uma dependência. Só arquiteto. */
export function useExcluirDep(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (depId: string) => api.del(`/api/v1/obras/${obraId}/dependencias/${depId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

/** Define a duração desejada (dias corridos) de uma tarefa. Só arquiteto. */
export function useSetDuracao(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { itemId: string; duracao_dias: number | null }) =>
      api.patch<Item>(`/api/v1/obras/${obraId}/itens/${v.itemId}/duracao`, {
        duracao_dias: v.duracao_dias,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

/** Recalcula as datas pela rede de dependências (forward pass FS). Devolve a árvore. */
export function useRecalcular(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { data_inicio?: string | null }) =>
      api.post<ChecklistTree>(`/api/v1/obras/${obraId}/cronograma/recalcular`, {
        data_inicio: v.data_inicio ?? null,
      }),
    onSuccess: (tree) => {
      qc.setQueryData(treeKey(obraId), tree)
      void qc.invalidateQueries({ queryKey: ["obra", obraId] })
    },
  })
}
