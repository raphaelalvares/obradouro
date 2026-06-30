import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { uuidv4 } from "@/lib/uuid"

export type StatusEtapa = "a_fazer" | "em_andamento" | "aguardando_cliente" | "concluida"
export type GateEtapa = "revisao" | "proposta" | "iniciar_obra" | null

/** Material curado pelo arquiteto numa etapa: ARQUIVO (PDF/imagem) ou LINK (tour 3D, vídeo…). */
export interface EtapaAnexo {
  id: string
  etapa: string
  tipo: "arquivo" | "link"
  label: string | null
  url: string | null // tipo='link'
  nome_arquivo: string | null // tipo='arquivo'
  content_type: string | null
  tamanho_bytes: number | null
  is_pdf: boolean
  tem_thumb: boolean
  ordem: number
  created_at: string
}

export interface EtapaProjeto {
  etapa: string
  rotulo: string
  ordem: number
  status: StatusEtapa
  data_prevista: string | null
  concluida_em: string | null
  decisao: string | null // só iniciar_obra: 'sim' | 'nao'
  observacao: string | null
  gate: GateEtapa
  acao_pendente: boolean // há uma ação do cliente esperando neste gate
  anexos: EtapaAnexo[] // material da etapa (arquivos/links)
}

export interface Pipeline {
  etapas: EtapaProjeto[]
  etapa_atual: string | null
}

const key = (projetoId: string) => ["pipeline", projetoId] as const

/** Linha do tempo do projeto (arquiteto e cliente). */
export function usePipeline(projetoId: string) {
  return useQuery({
    queryKey: key(projetoId),
    queryFn: () => api.get<Pipeline>(`/api/v1/projetos/${projetoId}/pipeline`),
    enabled: Boolean(projetoId),
  })
}

export interface EtapaPatch {
  status?: StatusEtapa
  data_prevista?: string | null
  observacao?: string | null
}

/** Arquiteto avança a etapa (status / data da medição / observação). */
export function useAtualizarEtapa(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { etapa: string } & EtapaPatch) => {
      const { etapa, ...body } = v
      return api.patch<Pipeline>(`/api/v1/projetos/${projetoId}/pipeline/${etapa}`, body)
    },
    onSuccess: (p) => qc.setQueryData(key(projetoId), p),
  })
}

/** Cliente decide iniciar a obra (sim/não) — gate final da linha do tempo. */
export function useDecidirIniciarObra(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (decisao: "sim" | "nao") =>
      api.post<Pipeline>(`/api/v1/projetos/${projetoId}/pipeline/iniciar-obra`, { decisao }),
    onSuccess: (p) => qc.setQueryData(key(projetoId), p),
  })
}

// ============================ material da etapa (arquivo | link) ============================
/** Arquiteto anexa um ARQUIVO (PDF/imagem) a uma etapa. */
export function useUploadEtapaArquivo(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { etapa: string; file: File; label?: string }) => {
      const fd = new FormData()
      fd.append("id", uuidv4())
      fd.append("arquivo", v.file)
      if (v.label?.trim()) fd.append("label", v.label.trim())
      return api.postForm<EtapaAnexo>(
        `/api/v1/projetos/${projetoId}/pipeline/${v.etapa}/anexos`,
        fd,
      )
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: key(projetoId) }),
  })
}

/** Arquiteto anexa um LINK (tour 3D, vídeo, pasta…) a uma etapa. */
export function useAdicionarEtapaLink(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { etapa: string; url: string; label?: string }) =>
      api.post<EtapaAnexo>(`/api/v1/projetos/${projetoId}/pipeline/${v.etapa}/anexos/link`, {
        id: uuidv4(),
        url: v.url.trim(),
        label: v.label?.trim() || null,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(projetoId) }),
  })
}

/** Arquiteto remove um anexo da etapa. */
export function useExcluirEtapaAnexo(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (anexoId: string) =>
      api.del(`/api/v1/projetos/${projetoId}/pipeline/anexos/${anexoId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(projetoId) }),
  })
}

/** Caminho dos bytes de um anexo de etapa do tipo arquivo (full|thumb) — fetch autenticado. */
export function conteudoEtapaAnexoPath(projetoId: string, anexoId: string, tipo: "full" | "thumb") {
  return `/api/v1/projetos/${projetoId}/pipeline/anexos/${anexoId}/conteudo?tipo=${tipo}`
}
