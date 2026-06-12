import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { uuidv4 } from "@/lib/uuid"

// ===================== tipos (espelham os schemas do backend) =====================
export interface OrcItem {
  id: string
  etapa: string
  ordem_etapa: number
  descricao: string
  ordem: number
  ambiente: string | null
  unidade: string | null
  quantidade: number | null
  valor_mo: number
  valor_material: number
  valor_equipamento: number
}

export interface OrcTotais {
  base_mo: number
  base_material: number
  base_equipamento: number
  mo: number
  material: number
  equipamento: number
  custo_direto: number
  bdi_valor: number
  imposto_valor: number
  preco_final: number
}

export interface OrcEtapaGrupo {
  etapa: string
  ordem_etapa: number
  custo_direto: number
  itens: OrcItem[]
}

export interface OrcAmbienteGrupo {
  ambiente: string | null
  custo_direto: number
  itens: OrcItem[]
}

export interface OrcVersao {
  id: string
  numero: number
  congelado: boolean
  data: string | null
  validade: string | null
  enviado: boolean
  enviado_em: string | null
  maj_mo: number
  maj_material: number
  maj_equipamento: number
  bdi: number
  imposto: number
  observacoes: string | null
  decisao: DecisaoAcao | null
  decisao_motivo: string | null
  decidido_em: string | null
  seq_humano: number | null
  created_at: string
  updated_at: string
  totais: OrcTotais
  etapas: OrcEtapaGrupo[]
  ambientes: OrcAmbienteGrupo[]
}

export interface OrcVersaoResumo {
  id: string
  numero: number
  congelado: boolean
  enviado: boolean
  decisao: DecisaoAcao | null
  data: string | null
  validade: string | null
  seq_humano: number | null
  created_at: string
  custo_direto: number
  preco_final: number
}

/** Linha da CENTRAL de orçamentos (cross-projeto) — espelha OrcamentoCentralOut do backend. */
export interface OrcamentoCentral {
  projeto_id: string
  projeto_nome: string
  projeto_seq: number | null
  tem_orcamento: boolean
  versao_id: string | null
  numero: number | null
  versao_seq: number | null
  enviado: boolean
  data: string | null
  validade: string | null
  atualizado_em: string | null
  n_versoes: number
  custo_direto: number
  preco_final: number
}

/** Linha/etapa da PROPOSTA (visão do cliente): só preço de VENDA — sem custos nem percentuais. */
export interface PropostaItem {
  descricao: string
  ambiente: string | null
  unidade: string | null
  quantidade: number | null
  valor: number
}

export interface PropostaEtapa {
  etapa: string
  valor: number
  itens: PropostaItem[]
}

export type DecisaoAcao = "aprovado" | "alteracao_pedida" | "recusado"

export interface PropostaResumo {
  id: string
  numero: number
  data: string | null
  validade: string | null
  enviado_em: string | null
  decisao: DecisaoAcao | null // null = pendente
  decidido_em: string | null
  preco_final: number
}

export interface Proposta extends PropostaResumo {
  observacoes: string | null
  decisao_motivo: string | null
  projeto_nome: string | null
  etapas: PropostaEtapa[]
}

export interface VirarObraOut {
  obra_id: string
  obra_nome: string
  obra_seq: number | null
  obra_criada: boolean
  etapas_novas: number
  etapas_existentes: number
  itens_novos: number
  itens_existentes: number
}

export interface ParamsPatch {
  data?: string | null
  validade?: string | null
  enviado?: boolean
  maj_mo?: number
  maj_material?: number
  maj_equipamento?: number
  bdi?: number
  imposto?: number
  observacoes?: string | null
}

export interface ItemForm {
  etapa: string
  descricao: string
  ordem_etapa?: number
  ordem?: number
  ambiente?: string | null
  unidade?: string | null
  quantidade?: number | null
  valor_mo?: number
  valor_material?: number
  valor_equipamento?: number
}

const base = (projetoId: string) => `/api/v1/projetos/${projetoId}/orcamento`
const versoesKey = (projetoId: string) => ["orcamento-versoes", projetoId] as const
const versaoKey = (projetoId: string, versaoId: string) =>
  ["orcamento-versao", projetoId, versaoId] as const

/** Central de orçamentos: 1 linha por projeto do arquiteto (versão atual + total). Cross-projeto. */
export function useCentralOrcamentos() {
  return useQuery({
    queryKey: ["orcamentos-central"],
    queryFn: () => api.get<OrcamentoCentral[]>("/api/v1/me/orcamentos"),
  })
}

export function useVersoes(projetoId: string) {
  return useQuery({
    queryKey: versoesKey(projetoId),
    queryFn: () => api.get<OrcVersaoResumo[]>(`${base(projetoId)}/versoes`),
    enabled: Boolean(projetoId),
  })
}

export function useVersao(projetoId: string, versaoId: string | null) {
  return useQuery({
    queryKey: versaoKey(projetoId, versaoId ?? ""),
    queryFn: () => api.get<OrcVersao>(`${base(projetoId)}/versoes/${versaoId}`),
    enabled: Boolean(projetoId && versaoId),
  })
}

export function useCriarVersao(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<OrcVersao>(`${base(projetoId)}/versoes`, { id: uuidv4() }),
    onSuccess: (v) => {
      qc.setQueryData(versaoKey(projetoId, v.id), v)
      void qc.invalidateQueries({ queryKey: versoesKey(projetoId) })
    },
  })
}

/** Toda mutação devolve a versão COMPLETA → atualiza o cache da versão na hora + a lista. */
function useVersaoMutation<TVars>(
  projetoId: string,
  versaoId: string,
  fn: (v: TVars) => Promise<OrcVersao>,
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (v) => {
      qc.setQueryData(versaoKey(projetoId, versaoId), v)
      void qc.invalidateQueries({ queryKey: versoesKey(projetoId) })
    },
  })
}

export function useAtualizarParams(projetoId: string, versaoId: string) {
  return useVersaoMutation<ParamsPatch>(projetoId, versaoId, (patch) =>
    api.patch<OrcVersao>(`${base(projetoId)}/versoes/${versaoId}`, patch),
  )
}

export function useAddItem(projetoId: string, versaoId: string) {
  return useVersaoMutation<ItemForm>(projetoId, versaoId, (v) =>
    api.post<OrcVersao>(`${base(projetoId)}/versoes/${versaoId}/itens`, {
      id: uuidv4(),
      ordem_etapa: 0,
      ordem: 0,
      valor_mo: 0,
      valor_material: 0,
      valor_equipamento: 0,
      ...v,
      descricao: v.descricao.trim(),
      etapa: v.etapa.trim(),
    }),
  )
}

export function useEditItem(projetoId: string, versaoId: string) {
  return useVersaoMutation<{ itemId: string; patch: Partial<ItemForm> }>(
    projetoId,
    versaoId,
    (v) => api.patch<OrcVersao>(`${base(projetoId)}/versoes/${versaoId}/itens/${v.itemId}`, v.patch),
  )
}

export function useExcluirItem(projetoId: string, versaoId: string) {
  return useVersaoMutation<string>(projetoId, versaoId, (itemId) =>
    api.del<OrcVersao>(`${base(projetoId)}/versoes/${versaoId}/itens/${itemId}`),
  )
}

export function useImportarOrcamento(projetoId: string, versaoId: string) {
  return useVersaoMutation<File>(projetoId, versaoId, (file) => {
    const fd = new FormData()
    fd.append("arquivo", file)
    return api.postForm<OrcVersao>(`${base(projetoId)}/versoes/${versaoId}/importar`, fd)
  })
}

export interface AplicarTemplateForm {
  template_id: string
  ambiente_nome: string
  area_m2?: number | null
}

export function useAplicarTemplate(projetoId: string, versaoId: string) {
  return useVersaoMutation<AplicarTemplateForm>(projetoId, versaoId, (v) =>
    api.post<OrcVersao>(`${base(projetoId)}/versoes/${versaoId}/aplicar-template`, v),
  )
}

/** Baixa o PDF da proposta (fetch com sessão → blob → download). Lança ApiError (ver isUpgrade). */
export async function baixarPropostaPdf(projetoId: string, versaoId: string, numero: number) {
  const blob = await api.getBlob(`${base(projetoId)}/versoes/${versaoId}/pdf`)
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `proposta-R${numero}.pdf`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}

// ===================== proposta (portal do cliente) =====================
export function usePropostas(projetoId: string) {
  return useQuery({
    queryKey: ["orcamento-propostas", projetoId],
    queryFn: () => api.get<PropostaResumo[]>(`${base(projetoId)}/proposta`),
    enabled: Boolean(projetoId),
  })
}

export function useProposta(projetoId: string, versaoId: string | null) {
  return useQuery({
    queryKey: ["orcamento-proposta", projetoId, versaoId ?? ""],
    queryFn: () => api.get<Proposta>(`${base(projetoId)}/proposta/${versaoId}`),
    enabled: Boolean(projetoId && versaoId),
  })
}

/** Cliente decide a proposta (aprovar/recusar/pedir alteração). Atualiza o cache da proposta + lista. */
export function useDecidirProposta(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { versaoId: string; acao: DecisaoAcao; motivo?: string | null }) =>
      api.post<Proposta>(`${base(projetoId)}/proposta/${v.versaoId}/decisao`, {
        acao: v.acao,
        motivo: v.motivo ?? null,
      }),
    onSuccess: (p) => {
      qc.setQueryData(["orcamento-proposta", projetoId, p.id], p)
      void qc.invalidateQueries({ queryKey: ["orcamento-propostas", projetoId] })
    },
  })
}

// ===================== virar obra =====================
export function useVirarObra(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (versaoId: string) =>
      api.post<VirarObraOut>(`${base(projetoId)}/versoes/${versaoId}/virar-obra`, {
        obra_id: uuidv4(), // id da obra NOVA (dual-ID); ignorado se o projeto já tem obra
      }),
    onSuccess: () => {
      // o vínculo do projeto pode ter mudado (obra criada) + o checklist da obra ganhou itens
      void qc.invalidateQueries({ queryKey: ["projeto", projetoId] })
      void qc.invalidateQueries({ queryKey: ["projetos"] })
      void qc.invalidateQueries({ queryKey: ["obras"] })
    },
  })
}
