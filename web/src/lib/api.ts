import { env } from "@/lib/env"

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

// B6 (BFF): a sessão vive em cookie httpOnly (o JS não a lê). O token CSRF é entregue no corpo do
// login/session e guardado AQUI em memória; reenviado no header X-CSRF-Token nas mutações (o
// CsrfMiddleware do backend valida header × cookie). setCsrf é chamado pelo @/auth/bff.
let _csrf: string | null = null
export function setCsrf(token: string | null): void {
  _csrf = token
}
export function getCsrf(): string | null {
  return _csrf
}

const _UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"])

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
  const headers: Record<string, string> = {}
  if (_UNSAFE.has(method) && _csrf) headers["X-CSRF-Token"] = _csrf
  let payload: BodyInit | undefined
  if (body instanceof FormData) {
    payload = body // multipart: o browser define o boundary, não setar content-type
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json"
    payload = JSON.stringify(body)
  }
  // credentials:'include' → o browser manda os cookies httpOnly de sessão p/ a API (cross-site).
  const res = await fetch(`${env.apiBaseUrl}${path}`, {
    method,
    headers,
    body: payload,
    credentials: "include",
  })
  return handle<T>(res)
}

/** GET de bytes (API-only: imagem trafega pela API com a sessão por cookie → o front faz blob URL,
 * pois <img src> autenticado não dá p/ apontar direto). */
async function requestBlob(path: string): Promise<Blob> {
  const res = await fetch(`${env.apiBaseUrl}${path}`, { method: "GET", credentials: "include" })
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
