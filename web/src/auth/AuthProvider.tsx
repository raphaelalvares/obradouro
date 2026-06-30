import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

import {
  bffBootstrap,
  bffLogin,
  bffLogout,
  bffOAuthUrl,
  bffSignup,
  type BffUser,
  type OAuthProvider,
} from "@/auth/bff"
import { watchIdle } from "@/auth/idle"
import { onSessionEnded } from "@/lib/api"

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
    // No boot (e ao voltar do OAuth, que é um page-load fresco): pergunta a sessão ao backend;
    // se o access expirou mas o refresh (janela de inatividade, 6h) ainda vive, bffBootstrap renova
    // antes de desistir.
    bffBootstrap()
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

  const signOut = useCallback(async () => {
    await bffLogout()
    setUser(null)
  }, [])

  // A sessão acabou no servidor (refresh falhou no meio de uma chamada) → limpa o estado e cai no
  // /login (o ProtectedRoute redireciona quando `session` fica null), sem esperar o reload.
  useEffect(() => onSessionEnded(() => setUser(null)), [])

  // Logout PROATIVO por inatividade (espelha a janela de 6h do backend); só roda enquanto logado.
  // O backend é a trava real (cookie deslizante + checagem no /refresh); aqui é só pra já mostrar o
  // login ao voltar parado. Local-first: limpa o estado na hora e desloga em background (best-effort),
  // pra não travar a UI no "logado" se o device voltar sem rede.
  useEffect(() => {
    if (!user) return
    return watchIdle(() => {
      setUser(null)
      void bffLogout()
    })
  }, [user])

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
      signOut,
    }),
    [user, loading, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth deve ser usado dentro de <AuthProvider>")
  return ctx
}
