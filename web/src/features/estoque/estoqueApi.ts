import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"

export interface NotaItem {
  id: string
  codigo: string | null
  descricao: string // nome fiel ao XML
  nome_editado: string | null
  nome: string // coalesce(nome_editado, descricao)
  ncm: string | null
  unidade: string | null
  quantidade_nota: number
  valor_unitario: number | null
  valor_total: number | null
  quantidade_conferida: number | null // null = não conferido
  conferido_por: string | null
  conferido_por_nome: string | null
  conferido_em: string | null
  divergente: boolean
  ordem: number
  created_at: string
}

export interface NotaResumo {
  id: string
  seq_humano: number | null
  numero: string | null
  serie: string | null
  chave_acesso: string | null
  emitente_nome: string | null
  emitente_cnpj: string | null
  data_emissao: string | null
  data_chegada: string | null
  valor_total: number
  total_itens: number
  itens_conferidos: number
  itens_divergentes: number
  created_at: string
}

export interface NotaDetalhe extends NotaResumo {
  itens: NotaItem[]
}

export interface SaldoItem {
  nome: string
  unidade: string | null
  fornecedor: string | null // emitente da NF-e (saldo agrupa por produto + fornecedor)
  notas: string | null // número(s) da(s) NF-e de origem
  data_chegada: string | null // chegada mais recente do grupo (se preenchida)
  quantidade_total: number
  valor_total: number
}

export interface ImportResumo {
  nota_id: string
  criada: boolean // false = já existia (idempotente pela chave)
  itens_novos: number
}

/** Status de conferência da nota, derivado das contagens (sem campo no banco). */
export type NotaStatus = "pendente" | "parcial" | "divergente" | "conferida"

export function notaStatus(n: {
  total_itens: number
  itens_conferidos: number
  itens_divergentes: number
}): NotaStatus {
  if (n.itens_divergentes > 0) return "divergente"
  if (n.total_itens === 0 || n.itens_conferidos === 0) return "pendente"
  if (n.itens_conferidos < n.total_itens) return "parcial"
  return "conferida"
}

const notasKey = (obraId: string) => ["estoque", obraId, "notas"] as const
const notaKey = (obraId: string, notaId: string) => ["estoque", obraId, "nota", notaId] as const
const saldoKey = (obraId: string) => ["estoque", obraId, "saldo"] as const

export function useNotas(obraId: string) {
  return useQuery({
    queryKey: notasKey(obraId),
    queryFn: () => api.get<NotaResumo[]>(`/api/v1/obras/${obraId}/estoque/notas`),
    enabled: Boolean(obraId),
  })
}

export function useNota(obraId: string, notaId: string | null) {
  return useQuery({
    queryKey: notaKey(obraId, notaId ?? ""),
    queryFn: () => api.get<NotaDetalhe>(`/api/v1/obras/${obraId}/estoque/notas/${notaId}`),
    enabled: Boolean(obraId && notaId),
  })
}

export function useSaldo(obraId: string) {
  return useQuery({
    queryKey: saldoKey(obraId),
    queryFn: () => api.get<SaldoItem[]>(`/api/v1/obras/${obraId}/estoque/saldo`),
    enabled: Boolean(obraId),
  })
}

export function useImportarNfe(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData()
      fd.append("arquivo", file)
      return api.postForm<ImportResumo>(`/api/v1/obras/${obraId}/estoque/importar`, fd)
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: notasKey(obraId) })
      void qc.invalidateQueries({ queryKey: saldoKey(obraId) })
    },
  })
}

export function useAtualizarNota(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { notaId: string; data_chegada: string | null }) =>
      api.patch<NotaDetalhe>(`/api/v1/obras/${obraId}/estoque/notas/${v.notaId}`, {
        data_chegada: v.data_chegada,
      }),
    onSuccess: (_d, v) => {
      void qc.invalidateQueries({ queryKey: notasKey(obraId) })
      void qc.invalidateQueries({ queryKey: notaKey(obraId, v.notaId) })
    },
  })
}

export function useExcluirNota(obraId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (notaId: string) => api.del(`/api/v1/obras/${obraId}/estoque/notas/${notaId}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: notasKey(obraId) })
      void qc.invalidateQueries({ queryKey: saldoKey(obraId) })
    },
  })
}

export function useConferirItem(obraId: string, notaId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { itemId: string; quantidade_conferida: number | null }) =>
      api.patch<NotaItem>(`/api/v1/obras/${obraId}/estoque/itens/${v.itemId}/conferencia`, {
        quantidade_conferida: v.quantidade_conferida,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: notaKey(obraId, notaId) })
      void qc.invalidateQueries({ queryKey: notasKey(obraId) })
      void qc.invalidateQueries({ queryKey: saldoKey(obraId) })
    },
  })
}

export function useEditarNomeItem(obraId: string, notaId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { itemId: string; nome_editado: string | null }) =>
      api.patch<NotaItem>(`/api/v1/obras/${obraId}/estoque/itens/${v.itemId}/nome`, {
        nome_editado: v.nome_editado,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: notaKey(obraId, notaId) })
      void qc.invalidateQueries({ queryKey: saldoKey(obraId) })
    },
  })
}
