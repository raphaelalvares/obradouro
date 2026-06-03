// Env tipado e validado uma vez (falha cedo e claro se faltar config).
function required(name: keyof ImportMetaEnv): string {
  const v = import.meta.env[name]
  if (!v) {
    throw new Error(
      `Variável de ambiente ausente: ${name}. Copie web/.env.example para .env.local e preencha.`,
    )
  }
  return v
}

export const env = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, ""),
  supabaseUrl: required("VITE_SUPABASE_URL"),
  supabaseAnonKey: required("VITE_SUPABASE_ANON_KEY"),
}
