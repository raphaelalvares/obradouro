import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react"

import {
  bffLogin,
  bffLogout,
  bffOAuthUrl,
  bffSession,
  bffSignup,
  type BffUser,
  type OAuthProvider,
} from "@/auth/bff"

export type { OAuthProvider }

interface SignUpParams {
  email: string
  password: string
  nome: string
  telefone?: string
}

interface AuthState {
  // B6: a sessão vive em cookie httpOnly; `session` é só o sinal de "logado" (mantém o contrato dos
  // consumidores que faziam `if (!session)`). `user` traz id/email vindos do backend.
  session: BffUser | null
  user: BffUser | null
  loading: boolean
  signIn: (email: string, password: string) => Promise<void>
  signUp: (params: SignUpParams) => Promise<{ precisaConfirmarEmail: boolean }>
  signInWithProvider: (provider: OAuthProvider) => Promise<void>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<BffUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let mounted = true
    // No boot (e ao voltar do OAuth, que é um page-load fresco): pergunta a sessão ao backend.
    bffSession()
      .then((u) => {
        if (mounted) {
          setUser(u)
          setLoading(false)
        }
      })
      .catch(() => {
        if (mounted) {
          setUser(null)
          setLoading(false)
        }
      })
    return () => {
      mounted = false
    }
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      session: user,
      user,
      loading,
      async signIn(email, password) {
        setUser(await bffLogin(email, password))
      },
      async signUp({ email, password, nome, telefone }) {
        const { user: novo, precisaConfirmarEmail } = await bffSignup({
          email,
          password,
          nome,
          telefone,
        })
        if (novo) setUser(novo) // autoconfirm: já entra (o <Navigate> das telas leva pra dentro)
        return { precisaConfirmarEmail }
      },
      async signInWithProvider(provider) {
        window.location.href = bffOAuthUrl(provider) // navegação top-level (sai da página)
      },
      async signOut() {
        await bffLogout()
        setUser(null)
      },
    }),
    [user, loading],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth deve ser usado dentro de <AuthProvider>")
  return ctx
}
