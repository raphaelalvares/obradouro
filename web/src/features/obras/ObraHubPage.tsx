import {
  Activity,
  ChartGantt,
  ChevronLeft,
  ChevronRight,
  HardHat,
  KeyRound,
  ListTree,
  Package,
  type LucideIcon,
} from "lucide-react"
import { useState } from "react"
import { Link, useParams } from "react-router-dom"

import { CenteredSpinner } from "@/components/feedback/states"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { useObra } from "@/features/obras/obrasApi"
import { AcessoClienteDialog } from "@/features/portal/AcessoClienteDialog"

interface Modulo {
  key: string
  title: string
  desc: string
  icon: LucideIcon
  to?: string // definido = ativo; ausente = "em breve" (a não ser que tenha onClick)
  onClick?: () => void // abre um dialog (ex.: acesso do cliente) — não é navegação
}

const MODULOS: Modulo[] = [
  // EAP/orçamento sustenta a árvore (etapas → tarefas + custo); o Cronograma agora é dedicado ao
  // tempo (Gantt). Mesmas rotas de hoje: a árvore em /cronograma, o Gantt em /cronograma/gantt.
  { key: "orcamento", title: "Orçamento / EAP", desc: "Etapas, custos e checklist", icon: ListTree, to: "cronograma" },
  { key: "cronograma", title: "Cronograma", desc: "Gantt e prazos", icon: ChartGantt, to: "cronograma/gantt" },
  { key: "estoque", title: "Estoque", desc: "Materiais e notas", icon: Package, to: "estoque" },
  { key: "acompanhamento", title: "Acompanhamento", desc: "Diário, pendências e avanço", icon: Activity, to: "acompanhamento" },
  { key: "prestadores", title: "Prestadores", desc: "Quem executa", icon: HardHat },
]

export function ObraHubPage() {
  const { obraId = "" } = useParams()
  const obra = useObra(obraId)
  const [acessoOpen, setAcessoOpen] = useState(false)
  const papel = obra.data?.meu_papel
  const ehArquiteto = papel === "arquiteto"
  // O CLIENTE no portal vê só o Acompanhamento (não os módulos do arquiteto: EAP/custos, estoque,
  // gantt, prestadores). Arquiteto/prestador seguem com a grade completa.
  const modulos = papel === "cliente" ? MODULOS.filter((m) => m.key === "acompanhamento") : MODULOS

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
          {modulos.map((m) => (
            <ModuloCard key={m.key} modulo={m} />
          ))}
          {/* Acesso do cliente direto na obra (sem projeto) — só arquiteto */}
          {ehArquiteto && (
            <ModuloCard
              modulo={{
                key: "acesso",
                title: "Acesso do cliente",
                desc: "Liberar o portal pro cliente",
                icon: KeyRound,
                onClick: () => setAcessoOpen(true),
              }}
            />
          )}
        </div>
      )}

      {ehArquiteto && (
        <AcessoClienteDialog
          alvo={{ tipo: "obra", id: obraId }}
          open={acessoOpen}
          onOpenChange={setAcessoOpen}
        />
      )}
    </div>
  )
}

function ModuloCard({ modulo }: { modulo: Modulo }) {
  const { icon: Icon, title, desc, to, onClick } = modulo
  const soon = !to && !onClick

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
  if (onClick) {
    return (
      <button type="button" onClick={onClick} className="block w-full text-left">
        {inner}
      </button>
    )
  }
  return (
    <Link to={to!} className="block">
      {inner}
    </Link>
  )
}
