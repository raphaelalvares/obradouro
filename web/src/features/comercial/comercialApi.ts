import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { uuidv4 } from "@/lib/uuid"

// Funil enxuto (poka-yoke; espelha o CHECK da migration 0058 e o Literal do backend).
export type EtapaOportunidade = "lead" | "contato" | "visita" | "proposta" | "ganho" | "perdido"

export interface Oportunidade {
  id: string
  nome: string
  etapa: EtapaOportunidade
  obra_id: string | null
  projeto_id: string | null
  contato_nome: string | null
  contato_telefone: string | null
  contato_email: string | null
  origem: string | null
  valor_estimado: number | null
  proximo_followup: string | null // "YYYY-MM-DD"
  observacoes: string | null
  comentarios_count: number
  seq_humano: number | null
  created_at: string
  updated_at: string
}

/** Comentário (timeline da negociação) — só o arquiteto/dono vê. */
export interface Comentario {
  id: string
  texto: string
  autor_nome: string | null
  created_at: string
  updated_at: string
}

/** Campos que o create/edit envia (id é gerado no cliente). */
export interface OportunidadeForm {
  nome: string
  etapa?: EtapaOportunidade
  contato_nome?: string | null
  contato_telefone?: string | null
  contato_email?: string | null
  origem?: string | null
  valor_estimado?: number | null
  proximo_followup?: string | null
  observacoes?: string | null
}

/** Obra devolvida pela conversão (ganho → obra). */
export interface ObraResumo {
  id: string
  nome: string
  seq_humano: number | null
}

// ===================== metadados das etapas (compartilhados pela UI) =====================
export interface EtapaMeta {
  key: EtapaOportunidade
  label: string
  cor: string // hex — usada em pontos/barras (igual ao Gantt: legível na tela)
  terminal?: boolean
}

// Progressão neutro→âmbar nos ativos; verde = ganho, vermelho = perdido (igual ao Gantt).
export const ETAPAS: EtapaMeta[] = [
  { key: "lead", label: "Lead", cor: "#938C7E" },
  { key: "contato", label: "Contato", cor: "#BF9A3A" },
  { key: "visita", label: "Visita", cor: "#D8A53A" },
  { key: "proposta", label: "Proposta", cor: "#E9C46A" },
  { key: "ganho", label: "Ganho", cor: "#5FB87A", terminal: true },
  { key: "perdido", label: "Perdido", cor: "#E5654B", terminal: true },
]

export const etapaMeta = (k: EtapaOportunidade): EtapaMeta =>
  ETAPAS.find((e) => e.key === k) ?? ETAPAS[0]

const KEY = ["oportunidades"] as const

export function useOportunidades() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => api.get<Oportunidade[]>("/api/v1/oportunidades"),
  })
}

export function useCriarOportunidade() {
  const qc = useQueryClient()
  return useMutation({
    // id gerado no cliente (offline/dual-ID); o backend atribui o seq_humano.
    mutationFn: (v: OportunidadeForm) =>
      api.post<Oportunidade>("/api/v1/oportunidades", { id: uuidv4(), ...v, nome: v.nome.trim() }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

/** PATCH parcial. UI OTIMISTA (move de etapa aparece na hora; reverte no erro). */
export function useAtualizarOportunidade() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; patch: Partial<OportunidadeForm> }) =>
      api.patch<Oportunidade>(`/api/v1/oportunidades/${v.id}`, v.patch),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: KEY })
      const prev = qc.getQueryData<Oportunidade[]>(KEY)
      if (prev) {
        qc.setQueryData<Oportunidade[]>(
          KEY,
          prev.map((o) => (o.id === v.id ? { ...o, ...v.patch } : o)),
        )
      }
      return { prev }
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(KEY, ctx.prev)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useExcluirOportunidade() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.del(`/api/v1/oportunidades/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

/** Converte a oportunidade (ganho) em obra. Devolve a obra criada (p/ navegar até ela). */
export function useConverterOportunidade() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (op: Oportunidade) =>
      api.post<ObraResumo>(`/api/v1/oportunidades/${op.id}/converter`, { obra_id: uuidv4() }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY })
      void qc.invalidateQueries({ queryKey: ["obras"] })
    },
  })
}

// ===================== elo com projeto =====================
/** Cria um projeto NOVO a partir do lead e vincula. Devolve o projeto criado (p/ navegar). */
export function useCriarProjetoDaOportunidade() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (op: Oportunidade) =>
      api.post<{ id: string; nome: string; seq_humano: number | null }>(
        `/api/v1/oportunidades/${op.id}/criar-projeto`,
        { projeto_id: uuidv4(), nome: op.nome },
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY })
      void qc.invalidateQueries({ queryKey: ["projetos"] })
    },
  })
}

/** Vincula (ou desvincula, projetoId=null) um projeto EXISTENTE à oportunidade. */
export function useVincularProjeto() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { opId: string; projetoId: string | null }) =>
      api.post<Oportunidade>(`/api/v1/oportunidades/${v.opId}/vincular-projeto`, {
        projeto_id: v.projetoId,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: KEY })
      void qc.invalidateQueries({ queryKey: ["projetos"] })
    },
  })
}

// ===================== comentários (timeline da negociação) =====================
const comentariosKey = (opId: string) => ["oportunidade-comentarios", opId] as const

export function useComentarios(opId: string) {
  return useQuery({
    queryKey: comentariosKey(opId),
    queryFn: () => api.get<Comentario[]>(`/api/v1/oportunidades/${opId}/comentarios`),
    enabled: Boolean(opId),
  })
}

export function useAddComentario(opId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (texto: string) =>
      api.post<Comentario>(`/api/v1/oportunidades/${opId}/comentarios`, {
        id: uuidv4(),
        texto: texto.trim(),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: comentariosKey(opId) })
      void qc.invalidateQueries({ queryKey: KEY }) // atualiza o contador no card
    },
  })
}

export function useEditComentario(opId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; texto: string }) =>
      api.patch<Comentario>(`/api/v1/oportunidades/${opId}/comentarios/${v.id}`, {
        texto: v.texto.trim(),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: comentariosKey(opId) }),
  })
}

export function useExcluirComentario(opId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.del(`/api/v1/oportunidades/${opId}/comentarios/${id}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: comentariosKey(opId) })
      void qc.invalidateQueries({ queryKey: KEY })
    },
  })
}
