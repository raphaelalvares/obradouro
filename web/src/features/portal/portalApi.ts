import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"

// ============================ tipos ============================
export interface PortalProjeto {
  id: string
  nome: string
  seq_humano: number | null
  obra_id: string | null
}

export interface PortalObra {
  id: string
  nome: string
  seq_humano: number | null
  status: string | null
}

/** Contexto de roteamento: o front manda o cliente PURO (eh_cliente && !eh_arquiteto) pro portal. */
export interface PortalContexto {
  eh_arquiteto: boolean
  eh_cliente: boolean
  projetos: PortalProjeto[]
  obras: PortalObra[]
}

export interface AcessoCliente {
  id: string
  email: string
  estado: string // 'pendente' (autorizado, aguardando) | 'ativo' (já entrou)
  cadastrado: boolean // já vinculou a conta (entrou no portal)
  projeto_id: string | null
  obra_id: string | null
  created_at: string
}

// ============================ chaves ============================
const CONTEXTO_KEY = ["portal-contexto"] as const

/** O acesso do cliente pode ser pendurado num PROJETO (proposta+obra) ou direto numa OBRA. */
export type AcessoAlvo = { tipo: "projeto" | "obra"; id: string }
const acessoBase = (a: AcessoAlvo) =>
  a.tipo === "projeto" ? `/api/v1/projetos/${a.id}/acessos` : `/api/v1/obras/${a.id}/acessos`
const acessosKey = (a: AcessoAlvo) => ["acessos-cliente", a.tipo, a.id] as const

/** URL pública que o arquiteto compartilha com o cliente (cadastro do portal). */
export function portalCadastroUrl(): string {
  return `${window.location.origin}/portal/cadastro`
}

// ============================ contexto (cliente: reconcilia + roteia) ============================
// POST porque reconcilia (idempotente). staleTime alto: roda 1× por sessão; o cliente recarrega se o
// arquiteto liberar o acesso enquanto ele já está logado (raro).
export function useContexto() {
  return useQuery({
    queryKey: CONTEXTO_KEY,
    queryFn: () => api.post<PortalContexto>("/api/v1/portal/sincronizar"),
    staleTime: 5 * 60 * 1000,
    retry: false,
  })
}

export function clienteEhPuro(ctx: PortalContexto | undefined): boolean {
  return Boolean(ctx?.eh_cliente && !ctx?.eh_arquiteto)
}

// ============================ arquiteto: acesso do cliente (projeto OU obra) ============================
export function useAcessos(alvo: AcessoAlvo, enabled = true) {
  return useQuery({
    queryKey: acessosKey(alvo),
    queryFn: () => api.get<AcessoCliente[]>(acessoBase(alvo)),
    enabled: enabled && Boolean(alvo.id),
  })
}

export function useAutorizarAcesso(alvo: AcessoAlvo) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (email: string) =>
      api.post<AcessoCliente>(acessoBase(alvo), { email: email.trim() }),
    onSuccess: () => qc.invalidateQueries({ queryKey: acessosKey(alvo) }),
  })
}

export function useRevogarAcesso(alvo: AcessoAlvo) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (acessoId: string) => api.del(`${acessoBase(alvo)}/${acessoId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: acessosKey(alvo) }),
  })
}
