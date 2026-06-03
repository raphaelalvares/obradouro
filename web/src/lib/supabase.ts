import { createClient } from "@supabase/supabase-js"

import { env } from "@/lib/env"

// Supabase é usado SÓ para auth no browser (login/sessão → JWT). Todo o dado vai pela API Python.
// persistSession + autoRefreshToken: o SDK guarda e renova a sessão; o api.ts lê o token a cada call.
export const supabase = createClient(env.supabaseUrl, env.supabaseAnonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
})
