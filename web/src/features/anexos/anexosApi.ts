import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { uuidv4 } from "@/lib/uuid"

export type ParentType = "etapa" | "checklist_item" | "diario" | "pendencia"

export interface Anexo {
  id: string
  parent_type: ParentType
  parent_id: string
  nome_arquivo: string
  content_type: string
  tamanho_bytes: number
  largura: number | null
  altura: number | null
  criado_por: string | null
  criado_por_nome: string | null
  seq_humano: number | null
  tem_thumb: boolean
  created_at: string
}

const listKey = (obraId: string, pt: ParentType, pid: string) =>
  ["anexos", obraId, pt, pid] as const

export function useAnexos(obraId: string, parentType: ParentType, parentId: string, enabled = true) {
  return useQuery({
    queryKey: listKey(obraId, parentType, parentId),
    queryFn: () =>
      api.get<Anexo[]>(
        `/api/v1/obras/${obraId}/anexos?parent_type=${parentType}&parent_id=${parentId}`,
      ),
    enabled: enabled && Boolean(obraId && parentId),
  })
}

export function useUploadAnexo(obraId: string, parentType: ParentType, parentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData()
      fd.append("id", uuidv4()) // id gerado no cliente (offline/dual-ID)
      fd.append("parent_type", parentType)
      fd.append("parent_id", parentId)
      fd.append("arquivo", file)
      return api.postForm<Anexo>(`/api/v1/obras/${obraId}/anexos`, fd)
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: listKey(obraId, parentType, parentId) }),
  })
}

export function useExcluirAnexo(obraId: string, parentType: ParentType, parentId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (anexoId: string) => api.del(`/api/v1/obras/${obraId}/anexos/${anexoId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: listKey(obraId, parentType, parentId) }),
  })
}

/** Caminho do conteúdo (full|thumb) — buscado por fetch autenticado (ver AnexoImage). */
export function conteudoPath(obraId: string, anexoId: string, tipo: "full" | "thumb") {
  return `/api/v1/obras/${obraId}/anexos/${anexoId}/conteudo?tipo=${tipo}`
}
