import { Loader2 } from "lucide-react"
import type { ReactNode } from "react"

import { Wordmark } from "@/components/brand/Wordmark"
import { Button } from "@/components/ui/button"
import { CenteredSpinner } from "@/components/feedback/states"
import { usePendentesAceite, useRegistrarAceite } from "@/features/auth/aceitesApi"

// Gate de aceite versionado (prova server-authoritative): se faltar aceitar a versão vigente dos
// documentos, bloqueia o app com um clickwrap explícito. Cobre OAuth, confirmação de e-mail em outro
// dispositivo, usuário antigo e re-aceite quando a versão muda. Cadastro por e-mail já vem atestado
// pelo metadata do signup (o backend auto-carimba), então normalmente não vê esta tela.
export function AceiteGate({ children }: { children: ReactNode }) {
  const { data, isLoading, isError } = usePendentesAceite(true)
  const registrar = useRegistrarAceite()

  if (isLoading) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <CenteredSpinner />
      </div>
    )
  }

  // Falha de rede não pode trancar o app inteiro — segue e revalida no próximo carregamento.
  if (isError || !data || data.length === 0) return <>{children}</>

  return (
    <div className="flex min-h-dvh flex-col justify-center px-6 py-12">
      <div className="animate-fade-up mx-auto w-full max-w-sm">
        <div className="mb-8 text-center">
          <Wordmark className="text-3xl" />
        </div>

        <h1 className="text-xl font-semibold">Antes de continuar</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Para usar o CRIA, você precisa concordar com os nossos termos.
        </p>

        <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
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
        </p>

        {registrar.isError && (
          <p className="mt-4 text-sm text-destructive" role="alert">
            Não foi possível registrar agora. Tente novamente.
          </p>
        )}

        <Button
          size="lg"
          className="mt-8 w-full"
          disabled={registrar.isPending}
          onClick={() => registrar.mutate("gate")}
        >
          {registrar.isPending && <Loader2 className="animate-spin" />}
          Aceito e quero continuar
        </Button>
      </div>
    </div>
  )
}
