import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { uuidv4 } from "@/lib/uuid"

// ===================== tipos (espelham schemas/acompanhamento.py) =====================
/** Linha do efetivo do dia: função × quantidade (nome = snapshot gravado no diário). */
export interface EfetivoItem {
  funcao_id: string
  nome: string
  qtd: number
}

export interface Diario {
  id: string
  data: string // "YYYY-MM-DD"
  texto: string
  clima: string | null
  efetivo: number | null // TOTAL (soma das qtds), mantido pelo backend
  efetivo_itens: EfetivoItem[]
  seq_humano: number | null
  created_by: string | null
  autor_nome: string | null
  n_fotos: number
  created_at: string
  updated_at: string
}

export interface DiarioForm {
  data: string
  texto: string
  clima?: string | null
  efetivo_itens?: { funcao_id: string; qtd: number }[]
}

export type Prioridade = "baixa" | "media" | "alta"
export type StatusPendencia = "aberta" | "resolvida"

export interface Pendencia {
  id: string
  descricao: string
  ambiente_id: string | null
  equipe_id: string | null
  prioridade: Prioridade
  status: StatusPendencia
  resolvido_por: string | null
  resolvido_por_nome: string | null
  resolvido_em: string | null
  seq_humano: number | null
  created_by: string | null
  autor_nome: string | null
  n_fotos: number
  created_at: string
  updated_at: string
}

export interface PendenciaForm {
  descricao: string
  ambiente_id?: string | null
  equipe_id?: string | null
  prioridade?: Prioridade
  status?: StatusPendencia
}

export interface CurvaPonto {
  data: string
  planejado_pct: number
  real_pct: number
}

export interface Avanco {
  por_custo: boolean
  peso_total: number
  real_pct: number
  planejado_pct: number
  inicio: string | null
  fim: string | null
  pontos: CurvaPonto[]
}

const diarioKey = (obraId: string) => ["diario", obraId] as const
const pendKey = (obraId: string) => ["pendencias", obraId] as const
const avancoKey = (obraId: string) => ["avanco", obraId] as const

/** invalida o diário E o que depende do progresso das medições (checklist + curva-S). Usado quando
 * apagar/editar um diário muda as medições de avanço (CASCADE ou re-datação do snapshot). */
function invalidarComProgresso(qc: QueryClient, obraId: string) {
  void qc.invalidateQueries({ queryKey: diarioKey(obraId) })
  void qc.invalidateQueries({ queryKey: ["checklist", obraId] })
  void qc.invalidateQueries({ queryKey: avancoKey(obraId) })
}

// ===================== diário =====================
export function useDiario(obraId: string) {
  return useQuery({
    queryKey: diarioKey(obraId),
    queryFn: () => api.get<Diario[]>(`/api/v1/obras/${obraId}/diario`),
    enabled: Boolean(obraId),
  })
}

export function useCriarDiario(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (form: DiarioForm) =>
      api.post<Diario>(`/api/v1/obras/${obraId}/diario`, { id: uuidv4(), ...form }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: diarioKey(obraId) }),
  })
}

export function useAtualizarDiario(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; patch: Partial<DiarioForm> }) =>
      api.patch<Diario>(`/api/v1/obras/${obraId}/diario/${v.id}`, v.patch),
    // mudar a DATA re-data os snapshots de avanço (recalc no backend) → checklist/curva-S mudam.
    onSuccess: () => invalidarComProgresso(qc, obraId),
  })
}

export function useExcluirDiario(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.del(`/api/v1/obras/${obraId}/diario/${id}`),
    // apagar o diário CASCADE-apaga as medições → o gatilho recalcula o progresso das folhas.
    onSuccess: () => invalidarComProgresso(qc, obraId),
  })
}

// ===================== pendências =====================
export function usePendencias(obraId: string) {
  return useQuery({
    queryKey: pendKey(obraId),
    queryFn: () => api.get<Pendencia[]>(`/api/v1/obras/${obraId}/pendencias`),
    enabled: Boolean(obraId),
  })
}

export function useCriarPendencia(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (form: PendenciaForm) =>
      api.post<Pendencia>(`/api/v1/obras/${obraId}/pendencias`, { id: uuidv4(), ...form }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: pendKey(obraId) }),
  })
}

export function useAtualizarPendencia(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; patch: Partial<PendenciaForm> }) =>
      api.patch<Pendencia>(`/api/v1/obras/${obraId}/pendencias/${v.id}`, v.patch),
    onSuccess: () => void qc.invalidateQueries({ queryKey: pendKey(obraId) }),
  })
}

export function useExcluirPendencia(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.del(`/api/v1/obras/${obraId}/pendencias/${id}`),
    onSuccess: () => void qc.invalidateQueries({ queryKey: pendKey(obraId) }),
  })
}

// ===================== avanço / curva S =====================
export function useAvanco(obraId: string) {
  return useQuery({
    queryKey: avancoKey(obraId),
    queryFn: () => api.get<Avanco>(`/api/v1/obras/${obraId}/acompanhamento/avanco`),
    enabled: Boolean(obraId),
  })
}
