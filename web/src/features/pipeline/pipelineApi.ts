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

export type StatusAprovacao3D = "rascunho" | "pendente" | "aprovado" | "alteracao_pedida"

/** Um cômodo do projeto na etapa Projeto 3D: material 3D + estado da aprovação por cômodo. */
export interface Ambiente3D {
  id: string
  nome: string
  ordem: number
  status_3d: StatusAprovacao3D
  motivo_3d: string | null
  decidido_por_3d: string | null
  decidido_por_nome: string | null
  decidido_em: string | null
  anexos: EtapaAnexo[] // renders/links 3D deste cômodo
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
  ambientes_3d: Ambiente3D[] // só na etapa projeto_3d (cômodos + aprovação por cômodo)
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

// ============================ 3D / aprovação por ambiente (etapa projeto_3d) ============================
const base3d = (projetoId: string) => `/api/v1/projetos/${projetoId}/pipeline/ambientes-3d`

/** Arquiteto cria um cômodo do projeto (estado inicial: rascunho). */
export function useCriarAmbiente3D(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (nome: string) =>
      api.post<Ambiente3D>(base3d(projetoId), { id: uuidv4(), nome }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(projetoId) }),
  })
}

/** Arquiteto renomeia um cômodo. */
export function useAtualizarAmbiente3D(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { ambId: string; nome: string }) =>
      api.patch<Ambiente3D>(`${base3d(projetoId)}/${v.ambId}`, { nome: v.nome }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(projetoId) }),
  })
}

/** Arquiteto remove um cômodo (e seu material 3D). */
export function useExcluirAmbiente3D(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ambId: string) => api.del(`${base3d(projetoId)}/${ambId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(projetoId) }),
  })
}

/** Arquiteto reordena os cômodos (otimista: a UI não fica refém do refetch entre cliques rápidos). */
export function useReordenarAmbientes3D(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) =>
      api.patch<Ambiente3D[]>(`${base3d(projetoId)}/reordenar`, { ids }),
    onMutate: async (ids) => {
      await qc.cancelQueries({ queryKey: key(projetoId) })
      const prev = qc.getQueryData<Pipeline>(key(projetoId))
      if (prev) {
        qc.setQueryData<Pipeline>(key(projetoId), {
          ...prev,
          etapas: prev.etapas.map((e) =>
            e.etapa === "projeto_3d"
              ? {
                  ...e,
                  ambientes_3d: ids
                    .map((id, i) => {
                      const r = e.ambientes_3d.find((x) => x.id === id)
                      return r ? { ...r, ordem: i } : null
                    })
                    .filter((x): x is Ambiente3D => x !== null),
                }
              : e,
          ),
        })
      }
      return { prev }
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(key(projetoId), ctx.prev)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: key(projetoId) }),
  })
}

/** Arquiteto envia o 3D do cômodo p/ aprovação (→ pendente). onSettled: ressincroniza no 409 de corrida. */
export function useEnviarAmbiente3D(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ambId: string) => api.post<Ambiente3D>(`${base3d(projetoId)}/${ambId}/enviar`, {}),
    onSettled: () => qc.invalidateQueries({ queryKey: key(projetoId) }),
  })
}

/** Cliente aprova ou pede alteração no 3D do cômodo. onSettled: ressincroniza no 409 (estado mudou). */
export function useDecidirAmbiente3D(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { ambId: string; acao: "aprovar" | "alteracao"; motivo?: string }) =>
      api.post<Ambiente3D>(`${base3d(projetoId)}/${v.ambId}/decisao`, {
        acao: v.acao,
        motivo: v.acao === "alteracao" ? (v.motivo?.trim() ?? null) : null,
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: key(projetoId) }),
  })
}

/** Arquiteto anexa um render (arquivo) ao cômodo. */
export function useUploadAnexoAmbiente3D(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { ambId: string; file: File; label?: string }) => {
      const fd = new FormData()
      fd.append("id", uuidv4())
      fd.append("arquivo", v.file)
      if (v.label?.trim()) fd.append("label", v.label.trim())
      return api.postForm<EtapaAnexo>(`${base3d(projetoId)}/${v.ambId}/anexos`, fd)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: key(projetoId) }),
  })
}

/** Arquiteto anexa um link 3D (tour, vídeo…) ao cômodo. */
export function useAdicionarLinkAmbiente3D(projetoId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { ambId: string; url: string; label?: string }) =>
      api.post<EtapaAnexo>(`${base3d(projetoId)}/${v.ambId}/anexos/link`, {
        id: uuidv4(),
        url: v.url.trim(),
        label: v.label?.trim() || null,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(projetoId) }),
  })
}
