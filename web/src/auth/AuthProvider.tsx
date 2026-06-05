import type { Session, User } from "@supabase/supabase-js"
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react"

import { supabase } from "@/lib/supabase"

export type OAuthProvider = "google" | "apple"

interface SignUpParams {
  email: string
  password: string
  nome: string
  telefone?: string
}

interface AuthState {
  session: Session | null
  user: User | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<void>
  signUp: (params: SignUpParams) => Promise<{ precisaConfirmarEmail: boolean }>
  signInWithProvider: (provider: OAuthProvider) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

// OAuth e o link de confirmação de e-mail voltam para esta rota (trata a sessão e redireciona).
function redirectTo(): string | undefined {
  return typeof window !== "undefined" ? `${window.location.origin}/auth/callback` : undefined
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return
      setSession(data.session)
      setLoading(false)
    })
    const { data: sub } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s)
    })
    return () => {
      mounted = false
      sub.subscription.unsubscribe()
    }
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      session,
      user: session?.user ?? null,
      loading,
      async signIn(email, password) {
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
      },
      async signUp({ email, password, nome, telefone }) {
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
          options: {
            // aceite atestado no metadata (viaja com o usuário p/ qualquer dispositivo): o backend
            // carimba a prova versionada no 1º acesso (GET /me/aceites/pendentes). O checkbox do
            // formulário é obrigatório p/ chegar aqui (CadastroPage).
            data: { nome, telefone: telefone ?? null, aceite: true },
            emailRedirectTo: redirectTo(),
          },
        })
        if (error) throw error
        // sem sessão = o projeto Supabase exige confirmação de e-mail antes do 1º login
        return { precisaConfirmarEmail: !data.session }
      },
      async signInWithProvider(provider) {
        const { error } = await supabase.auth.signInWithOAuth({
          provider,
          options: { redirectTo: redirectTo() },
        })
        if (error) throw error
      },
      async signOut() {
        await supabase.auth.signOut()
      },
    }),
    [session, loading],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth deve ser usado dentro de <AuthProvider>")
  return ctx
}
