import { Check, Circle, Clock, type LucideIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import type { EstadoItem } from "@/features/checklist/checklistApi"

const OPTS: { key: EstadoItem; label: string; Icon: LucideIcon; activeCls: string }[] = [
  { key: "pendente", label: "A fazer", Icon: Circle, activeCls: "bg-muted text-foreground" },
  {
    key: "em_andamento",
    label: "Fazendo",
    Icon: Clock,
    activeCls: "bg-[hsl(var(--estado-andamento))] text-black",
  },
  { key: "concluido", label: "Feito", Icon: Check, activeCls: "bg-primary text-primary-foreground" },
]

/**
 * Toggle de 3 estados (poka-yoke): só os 3 valores válidos, escolha explícita em 1 toque, sem
 * texto livre. O estado ativo é preenchido com a cor do estado.
 */
export function StateToggle({
  value,
  onChange,
  disabled,
  bloqueada,
}: {
  value: EstadoItem
  onChange: (estado: EstadoItem) => void
  disabled?: boolean
  /** bloqueada por dependência: desabilita AVANÇAR (em_andamento/concluido); "A fazer" segue livre
   * (espelha o backend, que sempre permite voltar p/ pendente). */
  bloqueada?: boolean
}) {
  return (
    <div className="inline-flex shrink-0 rounded-full border border-border p-0.5">
      {OPTS.map((o) => {
        const active = o.key === value
        const travado = disabled || (bloqueada && o.key !== "pendente")
        return (
          <button
            key={o.key}
            type="button"
            disabled={travado}
            onClick={() => !active && onChange(o.key)}
            aria-label={o.label}
            aria-pressed={active}
            title={o.label}
            className={cn(
              "flex size-8 items-center justify-center rounded-full transition-colors disabled:opacity-50",
              active ? o.activeCls : "text-muted-foreground hover:text-foreground",
            )}
          >
            <o.Icon className="size-4" />
          </button>
        )
      })}
    </div>
  )
}
