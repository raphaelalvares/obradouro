// Env do front. Tolerante a ausência de config: o app MONTA mesmo sem as chaves do Supabase
// (dá pra ver o design); só as chamadas de auth/API é que falham até preencher web/.env.local.
const rawSupabaseUrl = import.meta.env.VITE_SUPABASE_URL ?? ""
const rawSupabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY ?? ""

export const env = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, ""),
  // placeholders VÁLIDOS quando não configurado (createClient não aceita string vazia)
  supabaseUrl: rawSupabaseUrl || "http://localhost:54321",
  supabaseAnonKey: rawSupabaseKey || "anon-key-placeholder",
  supabaseConfigured: Boolean(rawSupabaseUrl && rawSupabaseKey),
}
