import { AlertTriangle, CreditCard, HardDrive, RotateCcw, X } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router-dom"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { useCobranca, useReativarAssinatura } from "@/features/conta/cobrancaApi"
import { usePlano } from "@/features/planos/planos"
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"

// Banners GLOBAIS de cobrança (montados no shell do arquiteto) — a jornada de expiry/up-sell não pode
// depender do usuário abrir Configurações. Prioriza pagamento recusado > cancelamento agendado; o de
// armazenamento é separado e dispensável por sessão. Sem cobrança/quota carregada, não renderiza nada.
const fmtData = (s: string) => new Date(s).toLocaleDateString("pt-BR")

function Bar({
  tone,
  icon,
  children,
}: {
  tone: "danger" | "warn"
  icon: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div
      className={cn(
        "border-b px-5 py-2",
        tone === "danger"
          ? "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400"
          : "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-500",
      )}
    >
      <div className="mx-auto flex max-w-5xl items-center gap-3 text-sm">
        {icon}
        {children}
      </div>
    </div>
  )
}

export function BillingBanners() {
  const { data: c } = useCobranca()
  const { quota } = usePlano()
  const reativar = useReativarAssinatura()
  const [quotaOff, setQuotaOff] = useState(
    () => sessionStorage.getItem("cria:quota-banner-off") === "1",
  )

  async function onReativar() {
    try {
      await reativar.mutateAsync()
      toast.success("Assinatura reativada", { description: "Volta a renovar normalmente." })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível reativar.")
    }
  }

  // 1) billing: pagamento recusado (crítico) tem prioridade sobre cancelamento agendado
  let billing: React.ReactNode = null
  if (c?.status === "past_due") {
    billing = (
      <Bar tone="danger" icon={<AlertTriangle className="size-4 shrink-0" />}>
        <span className="flex-1">
          <strong>Pagamento recusado.</strong> Regularize a fatura para não perder o acesso.
        </span>
        {c.fatura_pendente_url ? (
          <Button
            size="sm"
            onClick={() => {
              if (c.fatura_pendente_url) window.open(c.fatura_pendente_url, "_blank")
            }}
          >
            <CreditCard className="size-4" /> Pagar fatura
          </Button>
        ) : (
          <Link to="/configuracoes">
            <Button size="sm" variant="outline">
              Ver Financeiro
            </Button>
          </Link>
        )}
      </Bar>
    )
  } else if (c?.cancelamento_agendado) {
    billing = (
      <Bar tone="warn" icon={<AlertTriangle className="size-4 shrink-0" />}>
        <span className="flex-1">
          Sua assinatura será cancelada
          {c.current_period_end ? ` em ${fmtData(c.current_period_end)}` : ""}. Você mantém o acesso
          até lá.
        </span>
        <Button
          size="sm"
          variant="outline"
          onClick={onReativar}
          disabled={reativar.isPending}
          className="shrink-0"
        >
          <RotateCcw className="size-4" /> Reativar
        </Button>
      </Bar>
    )
  }

  // 2) armazenamento quase cheio (>= 90%) — up-sell in-app onipresente, dispensável por sessão
  const armaz = quota?.armazenamento
  const pct = armaz && armaz.limite_mb > 0 ? armaz.usado_bytes / (armaz.limite_mb * 1024 * 1024) : 0
  const quotaBanner =
    !quotaOff && pct >= 0.9 ? (
      <Bar tone="warn" icon={<HardDrive className="size-4 shrink-0" />}>
        <span className="flex-1">
          Seu armazenamento está em <strong>{Math.round(pct * 100)}%</strong> — amplie antes de
          travar os envios.
        </span>
        <Link to="/configuracoes" className="shrink-0">
          <Button size="sm" variant="outline">
            Ampliar espaço
          </Button>
        </Link>
        <button
          type="button"
          aria-label="Dispensar"
          onClick={() => {
            sessionStorage.setItem("cria:quota-banner-off", "1")
            setQuotaOff(true)
          }}
          className="shrink-0 rounded p-1 transition-colors hover:bg-black/5 dark:hover:bg-white/10"
        >
          <X className="size-4" />
        </button>
      </Bar>
    ) : null

  if (!billing && !quotaBanner) return null
  return (
    <div className="flex flex-col">
      {billing}
      {quotaBanner}
    </div>
  )
}
