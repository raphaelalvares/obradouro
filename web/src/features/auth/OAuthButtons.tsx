import { Loader2 } from "lucide-react"
import { useEffect, useState } from "react"

import { useAuth } from "@/auth/AuthProvider"
import { Button } from "@/components/ui/button"
import { env } from "@/lib/env"

// Login/cadastro social. Hoje só Google (Apple fica p/ quando houver Apple Developer Program). A prova
// de aceite NÃO é registrada aqui: quem entra por aqui passa pelo AceiteGate no app. O texto abaixo dá
// a ciência no momento do clique (clickwrap).
export function OAuthButtons() {
  const { signInWithProvider } = useAuth()
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  // Voltar do provedor pelo botão "voltar" (bfcache) não pode deixar o botão travado em loading.
  useEffect(() => {
    const reset = (e: PageTransitionEvent) => {
      if (e.persisted) setCarregando(false)
    }
    window.addEventListener("pageshow", reset)
    return () => window.removeEventListener("pageshow", reset)
  }, [])

  async function continuar() {
    setErro(null)
    if (!env.supabaseConfigured) {
      setErro("Ambiente não configurado — preencha as chaves do Supabase.")
      return
    }
    setCarregando(true)
    try {
      await signInWithProvider("google") // redireciona para o provedor (sai da página)
    } catch {
      setErro("Não foi possível continuar com Google.")
      setCarregando(false)
    }
  }

  return (
    <div className="space-y-3">
      <Button
        type="button"
        variant="outline"
        size="lg"
        className="w-full"
        disabled={carregando}
        onClick={() => void continuar()}
      >
        {carregando ? <Loader2 className="animate-spin" /> : <GoogleIcon />}
        Continuar com Google
      </Button>

      {erro && (
        <p className="text-sm text-destructive" role="alert">
          {erro}
        </p>
      )}

      <p className="text-center text-[11px] leading-relaxed text-muted-foreground">
        Ao continuar com Google, você concorda com os{" "}
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
