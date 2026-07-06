import { Sparkles } from "lucide-react"
import { useEffect, useState } from "react"
import { useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ApiError } from "@/lib/api"
import { EIXO_PLANO, planoLabel } from "@/features/planos/planos"

// Paywall GLOBAL desacoplado: qualquer lugar do app dispara um evento; o <PaywallHost/> (montado 1×
// no shell do arquiteto) escuta e abre o modal com o CTA de upgrade. Evita props/contexto e centraliza
// a mensagem de venda num único componente (antes: ~11 toasts soltos sem botão de ação).
interface PaywallDetail {
  eixo?: string
  titulo?: string
  detalhe?: string
}
const EVENTO = "cria:paywall"

/** Abre o paywall com o CTA de upgrade. Chame no clique de um recurso travado (proativo). */
export function abrirPaywall(detalhe: PaywallDetail = {}): void {
  window.dispatchEvent(new CustomEvent<PaywallDetail>(EVENTO, { detail: detalhe }))
}

/** Se o erro for um soft-limit (403 + upgrade_cta), abre o paywall e devolve true (o call-site não
 * precisa mostrar toast). Senão devolve false p/ o call-site tratar o erro como sempre. */
export function tratarUpsell(err: unknown): boolean {
  if (err instanceof ApiError && err.isUpgrade) {
    abrirPaywall({ eixo: err.problem?.eixo, detalhe: err.message })
    return true
  }
  return false
}

const TITULOS: Record<string, string> = {
  export_pdf: "Exporte com a sua marca",
  logo: "Sua marca nos documentos",
  obras_ativas: "Mais obras ao mesmo tempo",
  armazenamento: "Mais espaço para as fotos",
  portal: "Portal do cliente",
  chat: "Assistente com IA",
}

export function PaywallHost() {
  const [detalhe, setDetalhe] = useState<PaywallDetail | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    const handler = (e: Event) => setDetalhe((e as CustomEvent<PaywallDetail>).detail ?? {})
    window.addEventListener(EVENTO, handler)
    return () => window.removeEventListener(EVENTO, handler)
  }, [])

  const eixo = detalhe?.eixo
  const plano = eixo ? EIXO_PLANO[eixo] : undefined
  const titulo = (eixo && TITULOS[eixo]) || detalhe?.titulo || "Recurso de um plano superior"

  return (
    <Dialog open={detalhe !== null} onOpenChange={(o) => !o && setDetalhe(null)}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader className="items-center text-center">
          <div className="mx-auto mb-1 flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <Sparkles className="size-6" />
          </div>
          <DialogTitle>{titulo}</DialogTitle>
          <DialogDescription>
            {detalhe?.detalhe || "Este recurso faz parte de um plano superior."}
            {plano && (
              <>
                {" "}
                Disponível a partir do plano <strong>{planoLabel(plano)}</strong>.
              </>
            )}
          </DialogDescription>
        </DialogHeader>
        <div className="mt-2 flex flex-col-reverse gap-2 sm:flex-row sm:justify-center">
          <Button variant="ghost" onClick={() => setDetalhe(null)}>
            Agora não
          </Button>
          <Button
            onClick={() => {
              setDetalhe(null)
              navigate("/configuracoes")
            }}
          >
            Ver planos
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
