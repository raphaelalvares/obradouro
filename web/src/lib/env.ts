// Env do front. A autenticação é 100% via API (BFF, cookie httpOnly) — o front não fala mais
// direto com o Supabase, então só precisa saber a base da API.
export const env = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, ""),
}
