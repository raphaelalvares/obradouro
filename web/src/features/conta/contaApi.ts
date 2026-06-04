import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"

/** Plano + uso (espelha QuotaOut do backend). `flags` controla os recursos premium do front. */
export interface Quota {
  plano: string
  obras_ativas: { em_uso: number; limite: number }
  armazenamento: { usado_bytes: number; limite_mb: number }
  pode_criar_obra: boolean
  flags: Record<string, boolean>
}

export interface Branding {
  nome_escritorio: string | null
  tem_logo: boolean
  logo_mime: string | null
  pode_personalizar: boolean // flag 'logo' — front trava a seção e mostra upsell se false
}

/** Caminho dos bytes do logo (API-only → AnexoImage faz fetch autenticado e vira blob URL). */
export const LOGO_PATH = "/api/v1/me/branding/logo"

const quotaKey = ["quota"] as const
const brandingKey = ["branding"] as const

export function useQuota() {
  return useQuery({ queryKey: quotaKey, queryFn: () => api.get<Quota>("/api/v1/me/quota") })
}

export function useBranding() {
  return useQuery({ queryKey: brandingKey, queryFn: () => api.get<Branding>("/api/v1/me/branding") })
}

export function useSalvarBranding() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { nome_escritorio: string | null }) =>
      api.patch<Branding>("/api/v1/me/branding", v),
    onSuccess: (b) => qc.setQueryData(brandingKey, b),
  })
}

export function useUploadLogo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => {
      const fd = new FormData()
      fd.append("arquivo", file)
      return api.putForm<Branding>(LOGO_PATH, fd)
    },
    onSuccess: (b) => {
      qc.setQueryData(brandingKey, b)
      void qc.invalidateQueries({ queryKey: ["blob", LOGO_PATH] }) // refaz o preview
    },
  })
}

export function useRemoverLogo() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.del<Branding>(LOGO_PATH),
    onSuccess: (b) => {
      qc.setQueryData(brandingKey, b)
      void qc.invalidateQueries({ queryKey: ["blob", LOGO_PATH] })
    },
  })
}
