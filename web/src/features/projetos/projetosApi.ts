import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { ApiError, api } from "@/lib/api"
import { uuidv4 } from "@/lib/uuid"

// ============================ tipos ============================
export type PapelProjeto = "arquiteto" | "cliente"
export type StatusRevisao = "pendente" | "aprovado" | "alteracao_pedida" | "recusado"
export type AcaoRevisao = "aprovar" | "alteracao" | "recusar" | "escolher"

/** Briefing = onboarding estruturado. Backend guarda dict livre; o front fixa estes campos. */
export type Briefing = Record<string, string>

export interface Projeto {
  id: string
  nome: string
  obra_id: string | null
  briefing: Briefing
  revisoes_incluidas: number | null
  seq_humano: number | null
  created_at: string
  // papel do usuário corrente neste projeto — gateia a UI (arquiteto cura; cliente decide/visualiza)
  meu_papel: PapelProjeto | null
}

export interface ProjetoMembro {
  id: string
  profile_id: string
  nome: string | null
  email: string | null
  papel: string
  estado: string
  created_at: string
}

export interface ConviteEnviado {
  profile_id: string
  estado: string
}

export interface CodigoProjeto {
  codigo: string
  papel: string
  expires_at: string
}

export interface ProjetoPendente {
  projeto_id: string
  projeto_nome: string
  seq_humano: number | null
  invited_by_nome: string | null
}

export interface RevisaoArquivo {
  id: string
  nome_arquivo: string
  content_type: string
  tamanho_bytes: number
  largura: number | null
  altura: number | null
  is_pdf: boolean
  tem_thumb: boolean
  opcao: number | null // 1..9 quando a revisão traz opções de layout; null = sem opção
  created_at: string
}

export interface Revisao {
  id: string
  numero: number // R0 = entrega base; R1, R2… = alterações
  titulo: string | null
  status: StatusRevisao
  motivo: string | null
  decidido_por: string | null
  decidido_por_nome: string | null
  decidido_em: string | null
  opcao_escolhida: number | null // opção de layout que o cliente escolheu (revisão de opções)
  alem_do_incluido: boolean
  seq_humano: number | null
  created_at: string
  arquivos: RevisaoArquivo[]
}

export interface ContadorRevisoes {
  controla: boolean
  incluidas: number | null
  usadas: number
  restantes: number | null
  alem_count: number
}

export interface Secao {
  id: string
  nome: string
  ordem: number
  created_at: string
}

export interface MoodboardItem {
  id: string
  secao_id: string | null
  legenda: string | null
  nome_arquivo: string
  content_type: string
  tamanho_bytes: number
  largura: number | null
  altura: number | null
  ordem: number
  seq_humano: number | null
  tem_thumb: boolean
  created_at: string
}

// ============================ chaves ============================
const PROJETOS_KEY = ["projetos"] as const
const PENDENTES_KEY = ["projetos-pendentes"] as const
const projetoKey = (id: string) => ["projeto", id] as const
const membrosKey = (id: string) => ["projeto-membros", id] as const
const codigoKey = (id: string) => ["projeto-codigo", id] as const
const revisoesKey = (id: string) => ["revisoes", id] as const
const contadorKey = (id: string) => ["revisao-contador", id] as const
const secoesKey = (id: string) => ["moodboard-secoes", id] as const
const itensKey = (id: string) => ["moodboard-itens", id] as const

// ============================ projeto ============================
export function useProjetos() {
  return useQuery({
    queryKey: PROJETOS_KEY,
    queryFn: () => api.get<Projeto[]>("/api/v1/projetos"),
  })
}

export function useProjeto(id: string) {
  return useQuery({
    queryKey: projetoKey(id),
    queryFn: () => api.get<Projeto>(`/api/v1/projetos/${id}`),
    enabled: Boolean(id),
  })
}

export function useCriarProjeto() {
  const qc = useQueryClient()
  return useMutation({
    // id gerado no cliente (offline/dual-ID); o backend atribui o seq_humano e vincula o arquiteto.
    mutationFn: (v: { nome: string; revisoes_incluidas: number | null; briefing?: Briefing }) =>
      api.post<Projeto>("/api/v1/projetos", {
        id: uuidv4(),
        nome: v.nome.trim(),
        revisoes_incluidas: v.revisoes_incluidas,
        briefing: v.briefing ?? {},
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: PROJETOS_KEY }),
  })
}

export function useAtualizarProjeto(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (patch: {
      nome?: string
      briefing?: Briefing
      revisoes_incluidas?: number | null
    }) => api.patch<Projeto>(`/api/v1/projetos/${projetoId}`, patch),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: projetoKey(projetoId) })
      void qc.invalidateQueries({ queryKey: PROJETOS_KEY })
      void qc.invalidateQueries({ queryKey: contadorKey(projetoId) })
    },
  })
}

export function useVincularObra(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (obraId: string | null) =>
      api.post<Projeto>(`/api/v1/projetos/${projetoId}/vincular-obra`, { obra_id: obraId }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: projetoKey(projetoId) })
      void qc.invalidateQueries({ queryKey: PROJETOS_KEY })
    },
  })
}

// ============================ vínculo do próprio (pendentes/resgatar) ============================
export function useProjetosPendentes() {
  return useQuery({
    queryKey: PENDENTES_KEY,
    queryFn: () => api.get<ProjetoPendente[]>("/api/v1/me/projetos-pendentes"),
  })
}

export function useResgatarCodigo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (codigo: string) =>
      api.post<{ projeto_id: string; estado: string }>("/api/v1/projeto-codigo/resgatar", {
        codigo: codigo.trim().toUpperCase(),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PENDENTES_KEY })
      void qc.invalidateQueries({ queryKey: PROJETOS_KEY })
    },
  })
}

/** Aceitar por projeto_id (unicidade projeto+pessoa garante o vínculo pendente certo). */
export function useAceitarConvite() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (projetoId: string) =>
      api.post<{ projeto_id: string; estado: string }>(`/api/v1/projetos/${projetoId}/aceitar`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: PENDENTES_KEY })
      void qc.invalidateQueries({ queryKey: PROJETOS_KEY })
    },
  })
}

// ============================ membros / convites / código ============================
export function useMembros(projetoId: string, enabled = true) {
  return useQuery({
    queryKey: membrosKey(projetoId),
    queryFn: () => api.get<ProjetoMembro[]>(`/api/v1/projetos/${projetoId}/membros`),
    enabled: enabled && Boolean(projetoId),
  })
}

export function useConvidar(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (email: string) =>
      api.post<ConviteEnviado>(`/api/v1/projetos/${projetoId}/convites`, { email: email.trim() }),
    onSuccess: () => qc.invalidateQueries({ queryKey: membrosKey(projetoId) }),
  })
}

export function useRemoverMembro(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (membroId: string) =>
      api.del(`/api/v1/projetos/${projetoId}/membros/${membroId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: membrosKey(projetoId) }),
  })
}

export function useCodigo(projetoId: string, enabled = true) {
  return useQuery({
    queryKey: codigoKey(projetoId),
    // 404 = "nenhum código ativo" (estado normal) → devolve null (não vira erro: evita estado
    // inconsistente após gerar/revogar).
    queryFn: async (): Promise<CodigoProjeto | null> => {
      try {
        return await api.get<CodigoProjeto>(`/api/v1/projetos/${projetoId}/codigo`)
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null
        throw e
      }
    },
    enabled: enabled && Boolean(projetoId),
  })
}

export function useGerarCodigo(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<CodigoProjeto>(`/api/v1/projetos/${projetoId}/codigo`),
    onSuccess: (data) => qc.setQueryData(codigoKey(projetoId), data),
  })
}

export function useRevogarCodigo(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.del(`/api/v1/projetos/${projetoId}/codigo`),
    onSuccess: () => qc.invalidateQueries({ queryKey: codigoKey(projetoId) }),
  })
}

// ============================ revisões ============================
export function useRevisoes(projetoId: string) {
  return useQuery({
    queryKey: revisoesKey(projetoId),
    queryFn: () => api.get<Revisao[]>(`/api/v1/projetos/${projetoId}/revisoes`),
    enabled: Boolean(projetoId),
  })
}

export function useContador(projetoId: string) {
  return useQuery({
    queryKey: contadorKey(projetoId),
    queryFn: () => api.get<ContadorRevisoes>(`/api/v1/projetos/${projetoId}/revisoes/contador`),
    enabled: Boolean(projetoId),
  })
}

export function useSubirRevisao(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { titulo: string | null }) =>
      api.post<Revisao>(`/api/v1/projetos/${projetoId}/revisoes`, {
        id: uuidv4(),
        titulo: v.titulo?.trim() || null,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: revisoesKey(projetoId) })
      void qc.invalidateQueries({ queryKey: contadorKey(projetoId) })
    },
  })
}

export function useDecidirRevisao(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: {
      revisaoId: string
      acao: AcaoRevisao
      motivo?: string
      opcaoEscolhida?: number
    }) =>
      api.post<Revisao>(`/api/v1/projetos/${projetoId}/revisoes/${v.revisaoId}/decisao`, {
        acao: v.acao,
        motivo: v.motivo?.trim() || null,
        opcao_escolhida: v.acao === "escolher" ? (v.opcaoEscolhida ?? null) : null,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: revisoesKey(projetoId) })
      void qc.invalidateQueries({ queryKey: contadorKey(projetoId) })
    },
  })
}

export function useUploadArquivoRevisao(projetoId: string, revisaoId: string) {
  const qc = useQueryClient()
  return useMutation({
    // opcao: 1..9 marca o arquivo como uma opção de layout (1-de-N); null = arquivo comum.
    mutationFn: (v: { file: File; opcao?: number | null }) => {
      const fd = new FormData()
      fd.append("id", uuidv4())
      fd.append("arquivo", v.file)
      if (v.opcao != null) fd.append("opcao", String(v.opcao))
      return api.postForm<RevisaoArquivo>(
        `/api/v1/projetos/${projetoId}/revisoes/${revisaoId}/arquivos`,
        fd,
      )
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: revisoesKey(projetoId) }),
  })
}

export function useExcluirArquivoRevisao(projetoId: string, revisaoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (arquivoId: string) =>
      api.del(`/api/v1/projetos/${projetoId}/revisoes/${revisaoId}/arquivos/${arquivoId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: revisoesKey(projetoId) }),
  })
}

/** Caminho dos bytes do arquivo de revisão (full|thumb) — buscado via fetch autenticado. */
export function arquivoRevisaoPath(
  projetoId: string,
  revisaoId: string,
  arquivoId: string,
  tipo: "full" | "thumb",
) {
  return `/api/v1/projetos/${projetoId}/revisoes/${revisaoId}/arquivos/${arquivoId}/conteudo?tipo=${tipo}`
}

// ============================ moodboard ============================
export function useSecoes(projetoId: string) {
  return useQuery({
    queryKey: secoesKey(projetoId),
    queryFn: () => api.get<Secao[]>(`/api/v1/projetos/${projetoId}/moodboard/secoes`),
    enabled: Boolean(projetoId),
  })
}

export function useCriarSecao(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { nome: string; ordem: number }) =>
      api.post<Secao>(`/api/v1/projetos/${projetoId}/moodboard/secoes`, {
        id: uuidv4(),
        nome: v.nome.trim(),
        ordem: v.ordem,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: secoesKey(projetoId) }),
  })
}

export function useAtualizarSecao(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { secaoId: string; nome?: string; ordem?: number }) =>
      api.patch<Secao>(`/api/v1/projetos/${projetoId}/moodboard/secoes/${v.secaoId}`, {
        nome: v.nome,
        ordem: v.ordem,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: secoesKey(projetoId) }),
  })
}

export function useExcluirSecao(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (secaoId: string) =>
      api.del(`/api/v1/projetos/${projetoId}/moodboard/secoes/${secaoId}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: secoesKey(projetoId) })
      void qc.invalidateQueries({ queryKey: itensKey(projetoId) })
    },
  })
}

export function useItens(projetoId: string) {
  return useQuery({
    queryKey: itensKey(projetoId),
    queryFn: () => api.get<MoodboardItem[]>(`/api/v1/projetos/${projetoId}/moodboard/itens`),
    enabled: Boolean(projetoId),
  })
}

export function useUploadItem(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { file: File; secaoId: string | null; legenda?: string }) => {
      const fd = new FormData()
      fd.append("id", uuidv4())
      fd.append("arquivo", v.file)
      if (v.secaoId) fd.append("secao_id", v.secaoId)
      if (v.legenda) fd.append("legenda", v.legenda)
      return api.postForm<MoodboardItem>(`/api/v1/projetos/${projetoId}/moodboard/itens`, fd)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: itensKey(projetoId) }),
  })
}

export function useExcluirItem(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (itemId: string) =>
      api.del(`/api/v1/projetos/${projetoId}/moodboard/itens/${itemId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: itensKey(projetoId) }),
  })
}

/** Caminho dos bytes do item de moodboard (full|thumb) — fetch autenticado. */
export function itemMoodboardPath(projetoId: string, itemId: string, tipo: "full" | "thumb") {
  return `/api/v1/projetos/${projetoId}/moodboard/itens/${itemId}/conteudo?tipo=${tipo}`
}
