import { Loader2 } from "lucide-react"
import { useEffect, useState } from "react"

import { useAuth, type OAuthProvider } from "@/auth/AuthProvider"
import { Button } from "@/components/ui/button"
import { env } from "@/lib/env"

// Botões Google/Apple servem TANTO para cadastrar QUANTO para entrar (o provedor cria a conta no 1º
// acesso e reaproveita nos seguintes). A prova de aceite NÃO é registrada aqui: quem entra por OAuth
// passa pelo AceiteGate no app (clickwrap explícito). O texto abaixo dá a ciência no momento do clique.
export function OAuthButtons() {
  const { signInWithProvider } = useAuth()
  const [carregando, setCarregando] = useState<OAuthProvider | null>(null)
  const [erro, setErro] = useState<string | null>(null)

  // Volta do provedor pelo botão "voltar" (bfcache) não pode deixar os botões travados em loading.
  useEffect(() => {
    const reset = (e: PageTransitionEvent) => {
      if (e.persisted) setCarregando(null)
    }
    window.addEventListener("pageshow", reset)
    return () => window.removeEventListener("pageshow", reset)
  }, [])

  async function continuar(provider: OAuthProvider) {
    setErro(null)
    if (!env.supabaseConfigured) {
      setErro("Ambiente não configurado — preencha as chaves do Supabase.")
      return
    }
    setCarregando(provider)
    try {
      await signInWithProvider(provider) // redireciona para o provedor (sai da página)
    } catch {
      setErro(`Não foi possível continuar com ${provider === "google" ? "Google" : "Apple"}.`)
      setCarregando(null)
    }
  }

  return (
    <div className="space-y-3">
      <div className="space-y-2">
        <Button
          type="button"
          variant="outline"
          size="lg"
          className="w-full"
          disabled={carregando !== null}
          onClick={() => void continuar("google")}
        >
          {carregando === "google" ? <Loader2 className="animate-spin" /> : <GoogleIcon />}
          Continuar com Google
        </Button>
        <Button
          type="button"
          variant="outline"
          size="lg"
          className="w-full"
          disabled={carregando !== null}
          onClick={() => void continuar("apple")}
        >
          {carregando === "apple" ? <Loader2 className="animate-spin" /> : <AppleIcon />}
          Continuar com Apple
        </Button>
      </div>

      {erro && (
        <p className="text-sm text-destructive" role="alert">
          {erro}
        </p>
      )}

      <p className="text-center text-[11px] leading-relaxed text-muted-foreground">
        Ao continuar com Google ou Apple, você concorda com os{" "}
        <a href="/termos" target="_blank" rel="noreferrer" className="text-primary hover:underline">
          Termos de Uso
        </a>{" "}
        e a{" "}
        <a
          href="/privacidade"
          target="_blank"
          rel="noreferrer"
          className="text-primary hover:underline"
        >
          Política de Privacidade
        </a>
        .
      </p>
    </div>
  )
}

function GoogleIcon() {
  // Logo "G" multicolor oficial (cores fixas — não herdam currentColor de propósito).
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#FFC107"
        d="M43.611 20.083H42V20H24v8h11.303c-1.649 4.657-6.08 8-11.303 8-6.627 0-12-5.373-12-12s5.373-12 12-12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 12.955 4 4 12.955 4 24s8.955 20 20 20 20-8.955 20-20c0-1.341-.138-2.65-.389-3.917z"
      />
      <path
        fill="#FF3D00"
        d="m6.306 14.691 6.571 4.819C14.655 15.108 18.961 12 24 12c3.059 0 5.842 1.154 7.961 3.039l5.657-5.657C34.046 6.053 29.268 4 24 4 16.318 4 9.656 8.337 6.306 14.691z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.166 0 9.86-1.977 13.409-5.192l-6.19-5.238A11.91 11.91 0 0 1 24 36c-5.202 0-9.619-3.317-11.283-7.946l-6.522 5.025C9.505 39.556 16.227 44 24 44z"
      />
      <path
        fill="#1976D2"
        d="M43.611 20.083H42V20H24v8h11.303a12.04 12.04 0 0 1-4.087 5.571l.003-.002 6.19 5.238C36.971 39.205 44 34 44 24c0-1.341-.138-2.65-.389-3.917z"
      />
    </svg>
  )
}

function AppleIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M16.365 1.43c0 1.14-.493 2.27-1.177 3.08-.744.9-1.99 1.57-2.987 1.57-.12 0-.23-.02-.3-.03-.01-.06-.04-.22-.04-.39 0-1.15.572-2.27 1.206-2.98.804-.94 2.142-1.64 3.248-1.68.03.13.05.28.05.43zm4.565 15.71c-.03.07-.463 1.58-1.518 3.12-.945 1.34-1.94 2.71-3.43 2.71-1.517 0-1.9-.88-3.63-.88-1.698 0-2.302.91-3.67.91-1.377 0-2.332-1.26-3.428-2.8-1.287-1.82-2.323-4.63-2.323-7.28 0-4.28 2.797-6.55 5.552-6.55 1.448 0 2.675.95 3.6.95.865 0 2.222-1.01 3.902-1.01.613 0 2.886.06 4.374 2.19-.13.09-2.383 1.37-2.383 4.19 0 3.26 2.854 4.42 2.882 4.4z" />
    </svg>
  )
}
