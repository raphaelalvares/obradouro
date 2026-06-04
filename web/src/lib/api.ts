import { env } from "@/lib/env"
import { supabase } from "@/lib/supabase"

/** Problem Details (RFC 9457) que o backend usa p/ soft-limit (ex.: limite de obras ativas). */
export interface ApiProblem {
  type?: string
  title?: string
  status?: number
  detail?: string
  eixo?: string
  limite?: number
  atual?: number
  upgrade_cta?: boolean
  [k: string]: unknown
}

/** Erro normalizado de qualquer chamada à API. `problem` vem preenchido quando é problem+json. */
export class ApiError extends Error {
  status: number
  problem?: ApiProblem
  constructor(status: number, message: string, problem?: ApiProblem) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.problem = problem
  }
  /** Soft-limit (403 + upgrade_cta) — o front mostra o CTA de upgrade em vez de erro cru. */
  get isUpgrade() {
    return this.status === 403 && this.problem?.upgrade_cta === true
  }
  get isAuth() {
    return this.status === 401
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function parseError(res: Response): Promise<ApiError> {
  const ct = res.headers.get("content-type") ?? ""
  try {
    if (ct.includes("problem+json")) {
      const p = (await res.json()) as ApiProblem
      return new ApiError(res.status, p.detail ?? p.title ?? `Erro ${res.status}`, p)
    }
    if (ct.includes("json")) {
      const body = (await res.json()) as { detail?: unknown }
      const detail =
        typeof body.detail === "string" ? body.detail : `Erro ${res.status}`
      return new ApiError(res.status, detail)
    }
  } catch {
    /* corpo não-JSON ou vazio */
  }
  return new ApiError(res.status, `Erro ${res.status}`)
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  const ct = res.headers.get("content-type") ?? ""
  return ct.includes("json") ? ((await res.json()) as T) : (undefined as T)
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { ...(await authHeader()) }
  let payload: BodyInit | undefined
  if (body instanceof FormData) {
    payload = body // multipart: o browser define o boundary, não setar content-type
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json"
    payload = JSON.stringify(body)
  }
  const res = await fetch(`${env.apiBaseUrl}${path}`, { method, headers, body: payload })
  return handle<T>(res)
}

/** GET de bytes (API-only: imagem trafega pela API com Authorization → o front faz blob URL,
 * pois <img src> não envia o header do JWT). */
async function requestBlob(path: string): Promise<Blob> {
  const headers = { ...(await authHeader()) }
  const res = await fetch(`${env.apiBaseUrl}${path}`, { method: "GET", headers })
  if (!res.ok) throw await parseError(res)
  return res.blob()
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
  postForm: <T>(path: string, form: FormData) => request<T>("POST", path, form),
  putForm: <T>(path: string, form: FormData) => request<T>("PUT", path, form),
  getBlob: (path: string) => requestBlob(path),
}
