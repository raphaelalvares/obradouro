import { Loader2 } from "lucide-react"
import { useState, type FormEvent } from "react"
import { Navigate } from "react-router-dom"

import { useAuth } from "@/auth/AuthProvider"
import { Wordmark } from "@/components/brand/Wordmark"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { env } from "@/lib/env"

export function LoginPage() {
  const { session, loading, signIn } = useAuth()
  const [email, setEmail] = useState("")
  const [senha, setSenha] = useState("")
  const [erro, setErro] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  if (!loading && session) return <Navigate to="/" replace />

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    if (!env.supabaseConfigured) {
      setErro("Ambiente não configurado: preencha web/.env.local com as chaves do Supabase.")
      return
    }
    setEnviando(true)
    try {
      await signIn(email.trim(), senha)
    } catch {
      // mensagem genérica (não revela se o email existe — poka-yoke de segurança)
      setErro("E-mail ou senha incorretos.")
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="flex min-h-dvh flex-col justify-center px-6 py-12">
      <div className="mx-auto w-full max-w-sm">
        <div className="animate-fade-in mb-12 text-center">
          <Wordmark className="text-4xl" />
          <div className="mt-4 text-[10px] uppercase tracking-[0.35em] text-primary">
            Arquitetura · Obra · Gestão
          </div>
        </div>

        {!env.supabaseConfigured && (
          <div className="animate-fade-up mb-4 rounded-xl border border-primary/40 bg-primary/10 px-4 py-3 text-xs text-foreground">
            Ambiente não configurado — preencha <code>web/.env.local</code> com as chaves do
            Supabase para autenticar.
          </div>
        )}

        <form onSubmit={onSubmit} className="animate-fade-up space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="email">E-mail</Label>
            <Input
              id="email"
              type="email"
              inputMode="email"
              autoComplete="email"
              autoFocus
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="voce@estudio.com"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="senha">Senha</Label>
            <Input
              id="senha"
              type="password"
              autoComplete="current-password"
              required
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              placeholder="••••••••"
            />
          </div>

          {erro && (
            <p className="text-sm text-destructive" role="alert">
              {erro}
            </p>
          )}

          <Button
            type="submit"
            size="lg"
            className="w-full"
            disabled={enviando || !email || !senha}
          >
            {enviando && <Loader2 className="animate-spin" />}
            Entrar
          </Button>
        </form>

        <p className="animate-fade-up mt-8 text-center text-xs text-muted-foreground">
          Acesso do arquiteto · cada conta vê apenas suas obras
        </p>
      </div>
    </div>
  )
}
