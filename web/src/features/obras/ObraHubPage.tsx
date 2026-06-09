import {
  ChevronLeft,
  ChevronRight,
  HardHat,
  ListChecks,
  Package,
  UserRound,
  type LucideIcon,
} from "lucide-react"
import { Link, useParams } from "react-router-dom"

import { CenteredSpinner } from "@/components/feedback/states"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { useObra } from "@/features/obras/obrasApi"

interface Modulo {
  key: string
  title: string
  desc: string
  icon: LucideIcon
  to?: string // definido = ativo; ausente = "em breve"
}

const MODULOS: Modulo[] = [
  { key: "cronograma", title: "Cronograma", desc: "Etapas e checklist", icon: ListChecks, to: "cronograma" },
  { key: "estoque", title: "Estoque", desc: "Materiais e notas", icon: Package, to: "estoque" },
  { key: "prestadores", title: "Prestadores", desc: "Quem executa", icon: HardHat },
  { key: "cliente", title: "Cliente", desc: "Acompanhamento", icon: UserRound },
]

export function ObraHubPage() {
  const { obraId = "" } = useParams()
  const obra = useObra(obraId)

  return (
    <div className="animate-fade-up">
      <Link
        to="/"
        className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronLeft className="size-4" />
        Obras
      </Link>

      <div className="mb-6">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-primary">
          <span>Obra #{obra.data?.seq_humano ?? "—"}</span>
          {obra.data && (
            <span className="text-muted-foreground">
              · {obra.data.status === "ativa" ? "Ativa" : "Arquivada"}
            </span>
          )}
        </div>
        <h1 className="font-word text-3xl leading-tight break-words">{obra.data?.nome ?? "…"}</h1>
      </div>

      {obra.isLoading ? (
        <CenteredSpinner />
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {MODULOS.map((m) => (
            <ModuloCard key={m.key} modulo={m} />
          ))}
        </div>
      )}
    </div>
  )
}

function ModuloCard({ modulo }: { modulo: Modulo }) {
  const { icon: Icon, title, desc, to } = modulo
  const soon = !to

  const inner = (
    <Card
      className={cn(
        "flex h-full flex-col gap-3 p-5 transition-colors",
        soon ? "opacity-60" : "hover:border-primary/40",
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex size-11 items-center justify-center rounded-xl bg-accent text-primary">
          <Icon className="size-5" />
        </div>
        {soon ? (
          <span className="rounded-full border border-border px-2 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground">
            Em breve
          </span>
        ) : (
          <ChevronRight className="size-4 text-muted-foreground" />
        )}
      </div>
      <div>
        <h2 className="text-base font-medium">{title}</h2>
        <p className="text-xs text-muted-foreground">{desc}</p>
      </div>
    </Card>
  )

  if (soon) {
    return (
      <div aria-disabled className="cursor-default">
        {inner}
      </div>
    )
  }
  return (
    <Link to={to} className="block">
      {inner}
    </Link>
  )
}
