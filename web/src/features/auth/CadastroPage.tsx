import { Loader2, MailCheck } from "lucide-react"
import { useState, type FormEvent } from "react"
import { Link, Navigate } from "react-router-dom"

import { useAuth } from "@/auth/AuthProvider"
import { Wordmark } from "@/components/brand/Wordmark"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { OAuthButtons } from "@/features/auth/OAuthButtons"
import { env } from "@/lib/env"

export function CadastroPage() {
  const { session, loading, signUp } = useAuth()
  const [nome, setNome] = useState("")
  const [email, setEmail] = useState("")
  const [telefone, setTelefone] = useState("")
  const [senha, setSenha] = useState("")
  const [senha2, setSenha2] = useState("")
  const [aceito, setAceito] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [confirmarEmail, setConfirmarEmail] = useState(false)

  if (!loading && session) return <Navigate to="/" replace />

  const senhaCurta = senha.length > 0 && senha.length < 8
  const naoConfere = senha2.length > 0 && senha !== senha2
  const podeEnviar =
    nome.trim().length > 0 &&
    email.trim().length > 0 &&
    senha.length >= 8 &&
    senha === senha2 &&
    aceito

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setErro(null)
    if (!env.supabaseConfigured) {
      setErro("Ambiente não configurado: preencha web/.env.local com as chaves do Supabase.")
      return
    }
    if (!podeEnviar) return
    setEnviando(true)
    try {
      const { precisaConfirmarEmail } = await signUp({
        email: email.trim(),
        password: senha,
        nome: nome.trim(),
        telefone: telefone.trim() || undefined,
      })
      // com sessão imediata, o <Navigate> acima leva pra dentro quando o estado atualizar
      if (precisaConfirmarEmail) setConfirmarEmail(true)
    } catch (err) {
      const msg = err instanceof Error ? err.message.toLowerCase() : ""
      if (msg.includes("already") || msg.includes("registered") || msg.includes("exists")) {
        setErro("Este e-mail já tem conta. Faça login.")
      } else if (msg.includes("password") || msg.includes("senha")) {
        setErro("Senha fraca: use ao menos 8 caracteres.")
      } else {
        setErro("Não foi possível criar a conta. Tente novamente.")
      }
    } finally {
      setEnviando(false)
    }
  }

  if (confirmarEmail) {
    return (
      <div className="flex min-h-dvh flex-col justify-center px-6 py-12">
        <div className="animate-fade-up mx-auto w-full max-w-sm text-center">
          <div className="mx-auto mb-5 grid size-14 place-items-center rounded-2xl bg-primary/10 text-primary">
            <MailCheck className="size-7" />
          </div>
          <h1 className="text-xl font-semibold">Confirme seu e-mail</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Enviamos um link de confirmação para <span className="font-medium">{email.trim()}</span>.
            Abra o e-mail para ativar sua conta e entrar.
          </p>
          <Button asChild variant="outline" size="lg" className="mt-8 w-full">
            <Link to="/login">Voltar para o login</Link>
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-dvh flex-col justify-center px-6 py-12">
      <div className="mx-auto w-full max-w-sm">
        <div className="animate-fade-in mb-8 text-center">
          <Wordmark className="text-4xl" />
          <div className="mt-4 text-[10px] uppercase tracking-[0.35em] text-primary">
            Criar conta
          </div>
        </div>

        {!env.supabaseConfigured && (
          <div className="animate-fade-up mb-4 rounded-xl border border-primary/40 bg-primary/10 px-4 py-3 text-xs text-foreground">
            Ambiente não configurado — preencha <code>web/.env.local</code> com as chaves do
            Supabase para cadastrar.
          </div>
        )}

        <form onSubmit={onSubmit} className="animate-fade-up space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="nome">Nome</Label>
            <Input
              id="nome"
              type="text"
              autoComplete="name"
              required
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Seu nome"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="email">E-mail</Label>
            <Input
              id="email"
              type="email"
              inputMode="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="voce@estudio.com"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="telefone">Telefone (opcional)</Label>
            <Input
              id="telefone"
              type="tel"
              inputMode="tel"
              autoComplete="tel"
              value={telefone}
              onChange={(e) => setTelefone(e.target.value)}
              placeholder="(11) 90000-0000"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="senha">Senha</Label>
            <Input
              id="senha"
              type="password"
              autoComplete="new-password"
              required
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              placeholder="Mínimo de 8 caracteres"
            />
            {senhaCurta && (
              <p className="text-xs text-muted-foreground">Use ao menos 8 caracteres.</p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="senha2">Confirmar senha</Label>
            <Input
              id="senha2"
              type="password"
              autoComplete="new-password"
              required
              value={senha2}
              onChange={(e) => setSenha2(e.target.value)}
              placeholder="Repita a senha"
            />
            {naoConfere && <p className="text-xs text-destructive">As senhas não conferem.</p>}
          </div>

          <label className="flex items-start gap-2.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={aceito}
              onChange={(e) => setAceito(e.target.checked)}
              className="mt-0.5 size-4 shrink-0 rounded border-border accent-primary"
            />
            <span>
              Li e concordo com os{" "}
              <a
                href="/termos"
                target="_blank"
                rel="noreferrer"
                className="text-primary hover:underline"
              >
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
            </span>
          </label>

          {erro && (
            <p className="text-sm text-destructive" role="alert">
              {erro}
            </p>
          )}

          <Button type="submit" size="lg" className="w-full" disabled={enviando || !podeEnviar}>
            {enviando && <Loader2 className="animate-spin" />}
            Criar conta
          </Button>
        </form>

        <div className="animate-fade-up my-6 flex items-center gap-3">
          <span className="h-px flex-1 bg-border" />
          <span className="text-[10px] uppercase tracking-widest text-muted-foreground">ou</span>
          <span className="h-px flex-1 bg-border" />
        </div>

        <div className="animate-fade-up">
          <OAuthButtons />
        </div>

        <p className="animate-fade-up mt-8 text-center text-sm text-muted-foreground">
          Já tem conta?{" "}
          <Link to="/login" className="font-medium text-primary hover:underline">
            Entrar
          </Link>
        </p>
      </div>
    </div>
  )
}
