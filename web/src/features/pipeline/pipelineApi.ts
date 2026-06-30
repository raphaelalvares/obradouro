import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"

export type StatusEtapa = "a_fazer" | "em_andamento" | "aguardando_cliente" | "concluida"
export type GateEtapa = "revisao" | "proposta" | "iniciar_obra" | null

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
