import { Calculator, ChevronRight, HardHat, type LucideIcon } from "lucide-react"
import { Link } from "react-router-dom"

import { CenteredSpinner, ErrorState } from "@/components/feedback/states"
import { Card } from "@/components/ui/card"
import { useContexto } from "@/features/portal/portalApi"

/** Início do cliente: lista os projetos (proposta + revisões) e as obras (acompanhamento) dele.
 * Reusa as telas do arquiteto (gateadas por meu_papel) — daqui o cliente entra no hub do projeto
 * (ProjetoHubPage mostra a visão de cliente) e no acompanhamento da obra. */
export function PortalHomePage() {
  const ctx = useContexto()

  if (ctx.isLoading) return <CenteredSpinner />
  if (ctx.isError)
    return <ErrorState message="Não foi possível carregar seu portal." onRetry={() => void ctx.refetch()} />

  const projetos = ctx.data?.projetos ?? []
  const obras = ctx.data?.obras ?? []
  const vazio = projetos.length === 0 && obras.length === 0

  return (
    <div className="animate-fade-up space-y-8">
      <div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Seu portal</div>
        <h1 className="font-word text-3xl leading-tight">Acompanhe seu projeto</h1>
      </div>

      {vazio && (
        <Card className="p-6 text-center text-sm text-muted-foreground">
          Ainda não há nada para acompanhar. Assim que seu arquiteto liberar o projeto ou a obra, ele
          aparece aqui.
        </Card>
      )}

      {projetos.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-medium text-muted-foreground">Projetos</h2>
          <div className="space-y-3">
            {projetos.map((p) => (
              <ItemCard
                key={p.id}
                icon={Calculator}
                title={p.nome}
                desc="Proposta, revisões e aprovações"
                to={`/projetos/${p.id}`}
              />
            ))}
          </div>
        </section>
      )}

      {obras.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-medium text-muted-foreground">Obras</h2>
          <div className="space-y-3">
            {obras.map((o) => (
              <ItemCard
                key={o.id}
                icon={HardHat}
                title={o.nome}
                desc="Acompanhamento da obra (diário, pendências, avanço)"
                to={`/obras/${o.id}/acompanhamento`}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function ItemCard({
  icon: Icon,
  title,
  desc,
  to,
}: {
  icon: LucideIcon
  title: string
  desc: string
  to: string
}) {
  return (
    <Link to={to} className="block">
      <Card className="flex items-center gap-4 p-5 transition-colors hover:border-primary/40">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-accent text-primary">
          <Icon className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-base font-medium">{title}</h3>
          <p className="line-clamp-1 text-xs text-muted-foreground">{desc}</p>
        </div>
        <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
      </Card>
    </Link>
  )
}
