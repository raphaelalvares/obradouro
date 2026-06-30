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

/** Contexto de roteamento: o front manda pro portal quem é cliente e NÃO é arquiteto. */
export interface PortalContexto {
  eh_arquiteto: boolean
  eh_cliente: boolean
  // tem vínculo de cliente em algum lugar, mesmo VENCIDO — distingue cliente expirado de arquiteto novo
  tem_papel_cliente: boolean
  projetos: PortalProjeto[]
  obras: PortalObra[]
}

/** Prazo de validade do acesso (por e-mail). 'entrega' = vale até a obra ser marcada entregue. */
export type ValidadeTipo = "sem_prazo" | "data" | "entrega"

export interface AcessoCliente {
  id: string
  email: string
  estado: string // 'pendente' (autorizado, aguardando) | 'ativo' (já entrou)
  cadastrado: boolean // já vinculou a conta (entrou no portal)
  validade_tipo: ValidadeTipo
  validade_ate: string | null // 'YYYY-MM-DD' (só quando tipo === 'data')
  expira_em: string | null // derivado (data+1 / entrega→entregue_em da obra)
  expirado: boolean // o prazo já passou → acesso bloqueado (renovável)
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

/** Deve ver o PORTAL (shell do cliente)? É cliente em algum lugar (mesmo vencido) e não é arquiteto.
 * Inclui o cliente EXPIRADO (cai no portal com estado vazio, não no painel do arquiteto) e exclui o
 * arquiteto novo sem projetos (eh_arquiteto=false, mas tem_papel_cliente=false → painel). */
export function mostrarPortal(ctx: PortalContexto | undefined): boolean {
  return Boolean(ctx && ctx.tem_papel_cliente && !ctx.eh_arquiteto)
}

// ============================ arquiteto: acesso do cliente (projeto OU obra) ============================
export function useAcessos(alvo: AcessoAlvo, enabled = true) {
  return useQuery({
    queryKey: acessosKey(alvo),
    queryFn: () => api.get<AcessoCliente[]>(acessoBase(alvo)),
    enabled: enabled && Boolean(alvo.id),
  })
}

export interface PrazoInput {
  validade_tipo: ValidadeTipo
  validade_ate: string | null
}

export function useAutorizarAcesso(alvo: AcessoAlvo) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { email: string } & PrazoInput) =>
      api.post<AcessoCliente>(acessoBase(alvo), {
        email: v.email.trim(),
        validade_tipo: v.validade_tipo,
        validade_ate: v.validade_ate,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: acessosKey(alvo) }),
  })
}

/** Define/renova o prazo de um acesso já criado (PATCH). Reaplica o expira_em no backend. */
export function useDefinirPrazo(alvo: AcessoAlvo) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { acessoId: string } & PrazoInput) =>
      api.patch<AcessoCliente>(`${acessoBase(alvo)}/${v.acessoId}`, {
        validade_tipo: v.validade_tipo,
        validade_ate: v.validade_ate,
      }),
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
