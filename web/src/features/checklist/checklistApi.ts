import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { uuidv4 } from "@/lib/uuid"

export type EstadoItem = "pendente" | "em_andamento" | "concluido"

export interface Item {
  id: string
  etapa_id: string
  // subetapa à qual a Tarefa pertence (null = direto na etapa). SubTarefa herda o do pai.
  subetapa_id: string | null
  parent_item_id: string | null
  nome: string
  estado: EstadoItem
  // avanço parcial da FOLHA (0..100), mantido pelas medições do diário; null = sem medição → cai no
  // estado (concluido=100, senão 0). Em agregador é null (o progresso deriva dos filhos).
  progresso_pct: number | null
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
  // dependências valem na FOLHA: bloqueada = tem predecessor não-concluído;
  // aguarda = seq_humano dos predecessores que faltam concluir.
  bloqueada: boolean
  aguarda: number[]
  // cômodo (agrupamento) + orçamento (vindos do import ou editados à mão)
  ambiente: string | null // nome denormalizado (display); o vínculo é ambiente_id
  ambiente_id: string | null
  equipe_id: string | null // equipe responsável (cor/filtro no Gantt); biblioteca nível-tenant
  unidade: string | null
  quantidade: number | null
  custo_mao_obra: number | null
  custo_material: number | null
  custo_total: number | null
  // eh_folha = sem sub-itens. A FOLHA carrega o trabalho (estado/datas/duração/custo/dependências);
  // um item AGREGADOR (com sub-itens) tem datas DERIVADAS e não recebe esses controles.
  eh_folha: boolean
  // sub-itens (filhos manuais) — só vêm preenchidos nas tarefas com filhos
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

/** Campos editáveis de cômodo/orçamento/equipe (PATCH parcial). */
export interface ItemDetalhes {
  ambiente: string | null
  equipe_id: string | null
  unidade: string | null
  quantidade: number | null
  custo_mao_obra: number | null
  custo_material: number | null
  custo_total: number | null
}

/** Subetapa = agrupador entre Etapa e Tarefa (4º nível). Espelha a Etapa; vazia vira marco-folha. */
export interface Subetapa {
  id: string
  etapa_id: string
  nome: string
  ordem: number
  seq_humano: number | null
  updated_at: string
  data_inicio: string | null
  data_fim: string | null
  sem_itens: boolean // sem tarefas → datas/conclusão próprias (marco)
  concluida: boolean
  concluida_em: string | null
}

export interface SubetapaTree extends Subetapa {
  itens: Item[] // tarefas top-level desta subetapa
}

export interface Etapa {
  id: string
  nome: string
  ordem: number
  seq_humano: number | null
  updated_at: string
  // datas EFETIVAS: min/max dos filhos (subetapas + tarefas diretas); se vazia, as datas próprias.
  data_inicio: string | null
  data_fim: string | null
  sem_itens: boolean
  // conclusão manual da etapa (marco): só relevante p/ etapas vazias. Alimenta o Gantt.
  concluida: boolean
  concluida_em: string | null
  subetapas: SubetapaTree[] // agrupadores (4º nível)
  itens: Item[] // tarefas DIRETO na etapa (subetapa_id null; ragged)
}

/** Todas as tarefas top-level de uma etapa: as de cada subetapa + as diretas. A ordem (subetapas
 * antes das diretas) casa com a tela (EtapaCard renderiza subetapas primeiro) → Gantt e cronograma
 * macro ficam na mesma ordem que o usuário lê. */
export function tarefasDaEtapa(e: Etapa): Item[] {
  return [...e.subetapas.flatMap((s) => s.itens), ...e.itens]
}

/** Folhas (nós sem filhos) de uma lista de tarefas: a própria tarefa se folha, senão seus subitens. */
export function folhasDe(tarefas: Item[]): Item[] {
  return tarefas.flatMap((t) => (t.subitens.length > 0 ? t.subitens : [t]))
}

/** Progresso (0..1) de UMA folha: o avanço medido no diário (progresso_pct/100) se houver; senão o
 * binário do estado (concluído = 1). Fonte única do % parcial no front (tela, Gantt, %). */
export function progressoFolha(i: Item): number {
  if (i.progresso_pct != null) return Math.max(0, Math.min(1, i.progresso_pct / 100))
  return i.estado === "concluido" ? 1 : 0
}

/** Unidades de uma etapa p/ progresso/contador: as FOLHAS das tarefas (diretas + de subetapas) MAIS
 * cada subetapa-marco (sem tarefas) como 1 unidade. Não inclui a própria etapa-marco — quem chama
 * trata etapa vazia à parte. `feitos` = unidades 100% concluídas (contador "X/Y"); `progresso` =
 * avanço ponderado 0..1 (alimentado pelas medições do diário). Usado na tela (EtapaCard) e no Gantt. */
export function contagemEtapa(e: Etapa): { total: number; feitos: number; progresso: number } {
  let total = 0
  let feitos = 0
  let avanco = 0
  for (const f of folhasDe(tarefasDaEtapa(e))) {
    total += 1
    avanco += progressoFolha(f)
    if (f.estado === "concluido") feitos += 1
  }
  for (const s of e.subetapas) {
    if (s.sem_itens) {
      total += 1
      if (s.concluida) {
        feitos += 1
        avanco += 1
      }
    }
  }
  return { total, feitos, progresso: total > 0 ? avanco / total : 0 }
}

export interface CronogramaEntrada {
  tipo: "item" | "etapa" | "subetapa"
  id: string
  data_inicio: string | null
  data_fim: string | null
}

export interface Ambiente {
  id: string
  nome: string
  ordem: number
  area_m2: number | null
}

export interface ChecklistTree {
  obra_id: string
  etapas: Etapa[]
  dependencias: Dependencia[]
  ambientes: Ambiente[]
}

export interface ImportResumo {
  etapas_novas: number
  etapas_existentes: number
  itens_novos: number
  itens_existentes: number
}

// ---- atualizações OTIMISTAS da árvore (4 níveis ragged) ----
/** Aplica `fn` ao item com `id` em qualquer profundidade (tarefa direta, sob subetapa, ou subtarefa). */
function patchItens(itens: Item[], id: string, fn: (i: Item) => Item): Item[] {
  return itens.map((i) => {
    if (i.id === id) return fn(i)
    if (i.subitens.length > 0) return { ...i, subitens: patchItens(i.subitens, id, fn) }
    return i
  })
}

function patchEtapaItem(e: Etapa, id: string, fn: (i: Item) => Item): Etapa {
  return {
    ...e,
    itens: patchItens(e.itens, id, fn),
    subetapas: e.subetapas.map((s) => ({ ...s, itens: patchItens(s.itens, id, fn) })),
  }
}

/** Insere `novo` no lugar certo da etapa: como subtarefa do pai, sob a subetapa, ou direto na etapa.
 * Ao deixar de ser marco (1ª tarefa), zera datas/conclusão próprias — o backend passa a derivá-las
 * das tarefas, então mantê-las mostraria um intervalo/“concluída” fantasma até o refetch. */
function inserirItemEtapa(e: Etapa, novo: Item): Etapa {
  if (novo.parent_item_id) {
    const addFilho = (itens: Item[]) =>
      itens.map((t) =>
        t.id === novo.parent_item_id
          ? { ...t, eh_folha: false, subitens: [...t.subitens, novo] }
          : t,
      )
    return {
      ...e,
      itens: addFilho(e.itens),
      subetapas: e.subetapas.map((s) => ({ ...s, itens: addFilho(s.itens) })),
    }
  }
  if (novo.subetapa_id) {
    return {
      ...e,
      subetapas: e.subetapas.map((s) =>
        s.id === novo.subetapa_id
          ? {
              ...s,
              sem_itens: false,
              data_inicio: null,
              data_fim: null,
              concluida: false,
              concluida_em: null,
              itens: [...s.itens, novo],
            }
          : s,
      ),
    }
  }
  return {
    ...e,
    sem_itens: false,
    data_inicio: null,
    data_fim: null,
    concluida: false,
    concluida_em: null,
    itens: [...e.itens, novo],
  }
}

/** Remove o item `id` (em qualquer profundidade) — revert cirúrgico no erro de criação, sem
 * descartar inserções otimistas concorrentes (o snapshot inteiro apagaria irmãos ainda em voo). */
function removerItemEtapa(e: Etapa, id: string): Etapa {
  const filtra = (itens: Item[]): Item[] =>
    itens
      .filter((i) => i.id !== id)
      .map((i) => (i.subitens.length > 0 ? { ...i, subitens: filtra(i.subitens) } : i))
  return {
    ...e,
    itens: filtra(e.itens),
    subetapas: e.subetapas.map((s) => ({ ...s, itens: filtra(s.itens) })),
  }
}

const treeKey = (obraId: string) => ["checklist", obraId] as const

// As escritas OTIMISTAS da página (criar tarefa/subetapa, toggle, conclusão de etapa/subetapa)
// compartilham esta mutationKey. O invalidate da árvore só dispara quando é a ÚLTIMA escrita em voo
// (dentro de onSettled a própria mutation ainda conta → <= 1). Sem isso, em adições rápidas o
// refetch de uma sobrescrevia a inserção otimista da seguinte (item “some e volta”). Receita oficial
// do TanStack p/ invalidar uma única vez no fim da fila.
const writeKey = (obraId: string) => ["checklist-write", obraId] as const
function invalidarArvoreSeUltima(qc: QueryClient, obraId: string) {
  if (qc.isMutating({ mutationKey: writeKey(obraId) }) <= 1) {
    void qc.invalidateQueries({ queryKey: treeKey(obraId) })
  }
}

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
    mutationKey: writeKey(obraId),
    // id gerado no cliente (offline) → usado no POST e na inserção OTIMISTA do cache. parent_item_id
    // = SUB-TAREFA; subetapa_id = Tarefa sob uma subetapa; nenhum = Tarefa direto na etapa.
    mutationFn: (v: {
      id: string
      etapa_id: string
      nome: string
      parent_item_id?: string
      subetapa_id?: string
    }) =>
      api.post<Item>(`/api/v1/obras/${obraId}/itens`, {
        id: v.id,
        etapa_id: v.etapa_id,
        subetapa_id: v.subetapa_id ?? null,
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
        subetapa_id: v.subetapa_id ?? null,
        parent_item_id: v.parent_item_id ?? null,
        nome: v.nome.trim(),
        estado: "pendente",
        progresso_pct: null,
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
        ambiente_id: null,
        equipe_id: null,
        unidade: null,
        quantidade: null,
        custo_mao_obra: null,
        custo_material: null,
        custo_total: null,
        eh_folha: true,
        subitens: [],
      }
      if (prev) {
        qc.setQueryData<ChecklistTree>(treeKey(obraId), {
          ...prev,
          etapas: prev.etapas.map((e) => (e.id === v.etapa_id ? inserirItemEtapa(e, novo) : e)),
        })
      }
      return { prev }
    },
    // revert CIRÚRGICO: remove só o item que falhou (não restaura o snapshot inteiro, que apagaria
    // inserções otimistas concorrentes ainda em voo). O invalidate seguinte reconcilia o resto.
    onError: (_e, v) => {
      qc.setQueryData<ChecklistTree>(treeKey(obraId), (cur) =>
        cur ? { ...cur, etapas: cur.etapas.map((e) => removerItemEtapa(e, v.id)) } : cur,
      )
    },
    onSettled: () => invalidarArvoreSeUltima(qc, obraId),
  })
}

/** Toggle de estado com UI OTIMISTA (atualiza o cache antes da resposta; reverte no erro). */
export function useToggleItem(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: writeKey(obraId),
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
          etapas: prev.etapas.map((e) =>
            patchEtapaItem(e, v.item.id, (i) => ({ ...i, estado: v.estado })),
          ),
        })
      }
      return { prev }
    },
    // revert CIRÚRGICO: reaplica só o estado anterior deste item (v.item.estado), preservando toggles
    // otimistas concorrentes de outros itens (restaurar o snapshot inteiro os apagaria até o refetch).
    onError: (_e, v) => {
      qc.setQueryData<ChecklistTree>(treeKey(obraId), (cur) =>
        cur
          ? {
              ...cur,
              etapas: cur.etapas.map((e) =>
                patchEtapaItem(e, v.item.id, (i) => ({ ...i, estado: v.item.estado })),
              ),
            }
          : cur,
      )
    },
    onSettled: () => invalidarArvoreSeUltima(qc, obraId),
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
    mutationKey: writeKey(obraId),
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
    // revert cirúrgico: reaplica só a conclusão anterior desta etapa (preserva mudanças concorrentes).
    onError: (_e, v) => {
      qc.setQueryData<ChecklistTree>(treeKey(obraId), (cur) =>
        cur
          ? {
              ...cur,
              etapas: cur.etapas.map((e) =>
                e.id === v.etapa.id ? { ...e, concluida: v.etapa.concluida } : e,
              ),
            }
          : cur,
      )
    },
    onSettled: () => invalidarArvoreSeUltima(qc, obraId),
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

// ===================== subetapas (4º nível) =====================

/** Cria uma subetapa dentro de uma etapa. Só arquiteto. UI OTIMISTA (igual à criação de tarefa: o
 * AddInline limpa o campo na hora, então a subetapa precisa aparecer já). id gerado no cliente. */
export function useCriarSubetapa(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: writeKey(obraId),
    mutationFn: (v: { id: string; etapa_id: string; nome: string }) =>
      api.post<Subetapa>(`/api/v1/obras/${obraId}/subetapas`, {
        id: v.id,
        etapa_id: v.etapa_id,
        nome: v.nome.trim(),
      }),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: treeKey(obraId) })
      const prev = qc.getQueryData<ChecklistTree>(treeKey(obraId))
      const nova: SubetapaTree = {
        id: v.id,
        etapa_id: v.etapa_id,
        nome: v.nome.trim(),
        ordem: 9999,
        seq_humano: null,
        updated_at: new Date().toISOString(),
        data_inicio: null,
        data_fim: null,
        sem_itens: true,
        concluida: false,
        concluida_em: null,
        itens: [],
      }
      if (prev) {
        qc.setQueryData<ChecklistTree>(treeKey(obraId), {
          ...prev,
          etapas: prev.etapas.map((e) =>
            // a etapa deixa de ser marco ao ganhar uma subetapa (passa a derivar dos filhos)
            e.id === v.etapa_id
              ? {
                  ...e,
                  sem_itens: false,
                  data_inicio: null,
                  data_fim: null,
                  concluida: false,
                  concluida_em: null,
                  subetapas: [...e.subetapas, nova],
                }
              : e,
          ),
        })
      }
      return { prev }
    },
    // revert cirúrgico: remove só a subetapa que falhou (o invalidate reconcilia sem_itens da etapa).
    onError: (_e, v) => {
      qc.setQueryData<ChecklistTree>(treeKey(obraId), (cur) =>
        cur
          ? {
              ...cur,
              etapas: cur.etapas.map((e) => ({
                ...e,
                subetapas: e.subetapas.filter((s) => s.id !== v.id),
              })),
            }
          : cur,
      )
    },
    onSettled: () => invalidarArvoreSeUltima(qc, obraId),
  })
}

/** Renomeia uma subetapa. Só arquiteto. */
export function useRenomearSubetapa(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { subetapaId: string; nome: string }) =>
      api.patch<Subetapa>(`/api/v1/obras/${obraId}/subetapas/${v.subetapaId}`, {
        nome: v.nome.trim(),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

/** Exclui uma subetapa (e suas tarefas, por cascade). Só arquiteto. */
export function useExcluirSubetapa(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (subetapaId: string) =>
      api.del<{ deleted: boolean; itens_removidos: number }>(
        `/api/v1/obras/${obraId}/subetapas/${subetapaId}`,
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

/** Define início/fim direto na SUBETAPA (usada quando ela não tem tarefas). Só arquiteto. */
export function useSetSubetapaDatas(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { subetapaId: string; data_inicio: string | null; data_fim: string | null }) =>
      api.patch<Subetapa>(`/api/v1/obras/${obraId}/subetapas/${v.subetapaId}/datas`, {
        data_inicio: v.data_inicio,
        data_fim: v.data_fim,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

/** Marca/desmarca a SUBETAPA como concluída (marco; subetapas sem tarefas). Só arquiteto. */
export function useSetSubetapaConcluida(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationKey: writeKey(obraId),
    mutationFn: (v: { subetapa: SubetapaTree; concluida: boolean }) =>
      api.patch<Subetapa>(`/api/v1/obras/${obraId}/subetapas/${v.subetapa.id}/concluida`, {
        concluida: v.concluida,
        concluida_de: v.subetapa.concluida,
      }),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: treeKey(obraId) })
      const prev = qc.getQueryData<ChecklistTree>(treeKey(obraId))
      if (prev) {
        qc.setQueryData<ChecklistTree>(treeKey(obraId), {
          ...prev,
          etapas: prev.etapas.map((e) => ({
            ...e,
            subetapas: e.subetapas.map((s) =>
              s.id === v.subetapa.id ? { ...s, concluida: v.concluida } : s,
            ),
          })),
        })
      }
      return { prev }
    },
    // revert cirúrgico: reaplica só a conclusão anterior desta subetapa (preserva mudanças concorrentes).
    onError: (_e, v) => {
      qc.setQueryData<ChecklistTree>(treeKey(obraId), (cur) =>
        cur
          ? {
              ...cur,
              etapas: cur.etapas.map((e) => ({
                ...e,
                subetapas: e.subetapas.map((s) =>
                  s.id === v.subetapa.id ? { ...s, concluida: v.subetapa.concluida } : s,
                ),
              })),
            }
          : cur,
      )
    },
    onSettled: () => invalidarArvoreSeUltima(qc, obraId),
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

// ===================== ambientes / cômodos (Fatia A) =====================

/** Cria um cômodo no registro da obra. Só arquiteto. */
export function useCriarAmbiente(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { nome: string; area_m2?: number | null }) =>
      api.post<Ambiente>(`/api/v1/obras/${obraId}/ambientes`, {
        id: uuidv4(),
        nome: v.nome.trim(),
        area_m2: v.area_m2 ?? null,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

/** Renomeia / ajusta a área de um cômodo (rename propaga para os itens). Só arquiteto. */
export function useAtualizarAmbiente(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { ambId: string; nome?: string; area_m2?: number | null }) =>
      api.patch<Ambiente>(`/api/v1/obras/${obraId}/ambientes/${v.ambId}`, {
        nome: v.nome,
        area_m2: v.area_m2,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

/** Exclui um cômodo (desliga dos itens, sem apagá-los). Só arquiteto. */
export function useExcluirAmbiente(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ambId: string) => api.del(`/api/v1/obras/${obraId}/ambientes/${ambId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}

/** Reordena os cômodos (a posição na lista vira a ordem). Só arquiteto. */
export function useReordenarAmbientes(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) =>
      api.patch<Ambiente[]>(`/api/v1/obras/${obraId}/ambientes/reordenar`, { ids }),
    onSuccess: () => qc.invalidateQueries({ queryKey: treeKey(obraId) }),
  })
}
