// B6 (BFF): cliente dos endpoints de auth do backend. Substitui o supabase-js no browser — a sessão
// passa a viver em cookie httpOnly (fora do alcance de XSS). Tudo com credentials:'include' p/ os
// cookies trafegarem; o token CSRF do corpo é guardado no @/lib/api (memória) via setCsrf.
import { ApiError, getCsrf, setCsrf } from "@/lib/api"
import { env } from "@/lib/env"

const AUTH = `${env.apiBaseUrl}/api/v1/auth`

export type OAuthProvider = "google" | "apple"
export interface BffUser {
  id: string
  email: string | null
}

async function readJson(res: Response): Promise<Record<string, unknown>> {
  if (!res.ok) {
    let detail = `Erro ${res.status}`
    try {
      const b = (await res.json()) as { detail?: unknown }
      if (typeof b.detail === "string") detail = b.detail
    } catch {
      /* corpo vazio/não-JSON */
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as Record<string, unknown>
}

function toUser(data: Record<string, unknown>): BffUser {
  return { id: String(data.user_id), email: (data.email as string | null) ?? null }
}

export async function bffLogin(email: string, password: string): Promise<BffUser> {
  const res = await fetch(`${AUTH}/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  })
  const data = await readJson(res)
  setCsrf((data.csrf as string | null) ?? null)
  return toUser(data)
}

export interface SignupParams {
  email: string
  password: string
  nome: string
  telefone?: string
}

export async function bffSignup(
  params: SignupParams,
): Promise<{ user: BffUser | null; precisaConfirmarEmail: boolean }> {
  const res = await fetch(`${AUTH}/signup`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...params, telefone: params.telefone ?? null, aceite: true }),
  })
  const data = await readJson(res)
  const pendente = Boolean(data.precisa_confirmar_email)
  if (!pendente) setCsrf((data.csrf as string | null) ?? null)
  return { user: data.user_id ? toUser(data) : null, precisaConfirmarEmail: pendente }
}

/** Sessão atual (lê o cookie no servidor). null se não autenticado (401). Re-hidrata o CSRF. */
export async function bffSession(): Promise<BffUser | null> {
  const res = await fetch(`${AUTH}/session`, { credentials: "include" })
  if (res.status === 401) {
    setCsrf(null)
    return null
  }
  const data = await readJson(res)
  setCsrf((data.csrf as string | null) ?? null)
  return toUser(data)
}

export async function bffLogout(): Promise<void> {
  const headers: Record<string, string> = {}
  const csrf = getCsrf()
  if (csrf) headers["X-CSRF-Token"] = csrf // logout é cookie-auth → precisa do header CSRF
  try {
    await fetch(`${AUTH}/logout`, { method: "POST", credentials: "include", headers })
  } catch {
    /* best-effort: limpamos o estado local de qualquer forma */
  }
  setCsrf(null)
}

/** URL de início do OAuth (navegação top-level — o backend redireciona ao provedor). */
export function bffOAuthUrl(provider: OAuthProvider): string {
  return `${AUTH}/oauth/${provider}`
}
