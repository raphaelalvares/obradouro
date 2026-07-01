import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { uuidv4 } from "@/lib/uuid"

// DOIS funis no mesmo card (0088; poka-yoke, espelha os CHECK/Literals do backend):
// PROJETO (vender o projeto) e OBRA (conversão p/ obra). `etapa` (projeto) e `etapa_obra` (obra) são
// nulas quando o card não está naquele funil. Ganhar o projeto abre a obra ('a_orcar') — não é perda.
export type EtapaProjeto = "lead" | "contato" | "visita" | "proposta" | "ganho" | "perdido"
export type EtapaObra = "a_orcar" | "orcamento" | "apresentado" | "ganho" | "perdido"
/** retrocompat: alias do funil de projeto. */
export type EtapaOportunidade = EtapaProjeto

export interface Oportunidade {
  id: string
  nome: string
  etapa: EtapaProjeto | null // funil de projeto (null = card só-obra)
  etapa_obra: EtapaObra | null // funil de obra (null = card só-projeto)
  obra_id: string | null
  projeto_id: string | null
  contato_nome: string | null
  contato_telefone: string | null
  contato_email: string | null
  origem: string | null
  valor_estimado: number | null // valor do projeto
  valor_obra: number | null // valor da obra
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
  etapa?: EtapaProjeto | null
  etapa_obra?: EtapaObra | null
  contato_nome?: string | null
  contato_telefone?: string | null
  contato_email?: string | null
  origem?: string | null
  valor_estimado?: number | null
  valor_obra?: number | null
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
  key: string
  label: string
  cor: string // hex — usada em pontos/barras (igual ao Gantt: legível na tela)
  terminal?: boolean
}

// Progressão neutro→âmbar nos ativos; verde = ganho, vermelho = perdido (igual ao Gantt).
// PROJETO: "Visita" é rotulada "Medição" (o fluxo começa no agendamento de medição); valor salvo
// segue "visita".
export const ETAPAS_PROJETO: EtapaMeta[] = [
  { key: "lead", label: "Lead", cor: "#938C7E" },
  { key: "contato", label: "Contato", cor: "#BF9A3A" },
  { key: "visita", label: "Medição", cor: "#D8A53A" },
  { key: "proposta", label: "Proposta", cor: "#E9C46A" },
  { key: "ganho", label: "Ganho", cor: "#5FB87A", terminal: true },
  { key: "perdido", label: "Perdido", cor: "#E5654B", terminal: true },
]

// OBRA: sincronizado com o orçamento (a_orcar→orcamento→apresentado→ganho/perdido).
export const ETAPAS_OBRA: EtapaMeta[] = [
  { key: "a_orcar", label: "A orçar", cor: "#938C7E" },
  { key: "orcamento", label: "Orçamento", cor: "#BF9A3A" },
  { key: "apresentado", label: "Apresentado", cor: "#D8A53A" },
  { key: "ganho", label: "Ganho", cor: "#5FB87A", terminal: true },
  { key: "perdido", label: "Perdido", cor: "#E5654B", terminal: true },
]

/** retrocompat: ETAPAS = funil de projeto. */
export const ETAPAS = ETAPAS_PROJETO

const metaDe = (etapas: EtapaMeta[], k: string | null): EtapaMeta =>
  etapas.find((e) => e.key === k) ?? etapas[0]

export const etapaMeta = (k: string | null): EtapaMeta => metaDe(ETAPAS_PROJETO, k)
export const etapaObraMeta = (k: string | null): EtapaMeta => metaDe(ETAPAS_OBRA, k)

// ===================== descritor de funil (parametriza a página/diálogos) =====================
export type FunilKey = "projeto" | "obra"

export interface Funil {
  key: FunilKey
  label: string
  etapas: EtapaMeta[]
  /** etapa do card NESTE funil (null = card fora do funil). */
  getEtapa: (o: Oportunidade) => string | null
  getValor: (o: Oportunidade) => number | null
  meta: (k: string | null) => EtapaMeta
  /** patch parcial p/ mover a etapa deste funil. */
  patchEtapa: (etapa: string) => Partial<OportunidadeForm>
  /** patch parcial p/ o valor deste funil. */
  patchValor: (v: number | null) => Partial<OportunidadeForm>
  valorLabel: string
  /** etapa inicial ao cadastrar entrando neste funil. */
  entrada: Partial<OportunidadeForm>
}

export const FUNIS: Record<FunilKey, Funil> = {
  projeto: {
    key: "projeto",
    label: "Projeto",
    etapas: ETAPAS_PROJETO,
    getEtapa: (o) => o.etapa,
    getValor: (o) => o.valor_estimado,
    meta: etapaMeta,
    patchEtapa: (etapa) => ({ etapa: etapa as EtapaProjeto }),
    patchValor: (v) => ({ valor_estimado: v }),
    valorLabel: "Valor do projeto",
    entrada: { etapa: "lead" },
  },
  obra: {
    key: "obra",
    label: "Obra",
    etapas: ETAPAS_OBRA,
    getEtapa: (o) => o.etapa_obra,
    getValor: (o) => o.valor_obra,
    meta: etapaObraMeta,
    patchEtapa: (etapa) => ({ etapa_obra: etapa as EtapaObra }),
    patchValor: (v) => ({ valor_obra: v }),
    valorLabel: "Valor da obra",
    entrada: { etapa_obra: "a_orcar" },
  },
}

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

// ===================== elo com portal (costura lead → portal) =====================
/** Resposta do "liberar portal": e-mail do lead usado + se o convite foi ENVIADO agora (1ª vez)
 * + se o cliente já entrou — o front usa isso p/ um toast honesto. */
export interface LiberarPortalResult {
  email: string
  cadastrado: boolean
  convite_enviado: boolean
}

/** Libera o acesso do cliente no portal usando o e-mail de contato do lead (sem redigitar) e
 * dispara o link de cadastro por e-mail. Invalida o cache do portal (acessos do projeto/obra). */
export function useLiberarPortalDaOportunidade() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (opId: string) =>
      api.post<LiberarPortalResult>(`/api/v1/oportunidades/${opId}/liberar-portal`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["portal"] }),
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
