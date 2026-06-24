import { Bell, ChevronDown } from "lucide-react"
import { useState } from "react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { SEV_META, useLembretes, type Apontamento } from "@/features/comercial/lembretesApi"

const VISIVEIS = 3

/** Card de lembretes do funil. Some quando não há nada/erro/carregando — nunca compete com o Kanban
 * nem quebra a página. `onAbrir` abre o detalhe da oportunidade. */
export function LembretesCard({ onAbrir }: { onAbrir: (opId: string) => void }) {
  const q = useLembretes()
  const [tudo, setTudo] = useState(false)

  if (!q.isSuccess || q.data.length === 0) return null

  const aps = tudo ? q.data : q.data.slice(0, VISIVEIS)
  const restante = q.data.length - aps.length

  return (
    <Card className="mb-6">
      <CardHeader className="flex-row items-center gap-2 pb-3">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Bell className="size-4 text-primary" />
          Lembretes
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs tabular-nums text-muted-foreground">
            {q.data.length}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-1.5 pt-0">
        {aps.map((a) => (
          <LinhaLembrete key={`${a.id_oportunidade}-${a.regra_id}`} a={a} onAbrir={onAbrir} />
        ))}
        {(restante > 0 || tudo) && (
          <button
            type="button"
            onClick={() => setTudo((v) => !v)}
            className="mt-1 inline-flex items-center gap-1 self-start text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            <ChevronDown className={cn("size-3.5 transition-transform", tudo && "rotate-180")} />
            {tudo ? "Ver menos" : `Ver todos (${restante} a mais)`}
          </button>
        )}
      </CardContent>
    </Card>
  )
}

function LinhaLembrete({ a, onAbrir }: { a: Apontamento; onAbrir: (opId: string) => void }) {
  const sev = SEV_META[a.severidade]
  return (
    <button
      type="button"
      onClick={() => onAbrir(a.id_oportunidade)}
      className="flex w-full items-start gap-2.5 rounded-xl border border-border bg-card px-3 py-2 text-left transition-colors hover:border-primary/40"
    >
      <span
        className="mt-1 size-2 shrink-0 rounded-full"
        style={{ background: sev.cor }}
        aria-hidden
      />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline gap-1.5">
          <span className="shrink-0 font-display text-[11px] text-muted-foreground">
            #{a.seq_humano ?? "—"}
          </span>
          <span className="min-w-0 break-words text-sm font-medium">{a.nome}</span>
        </span>
        <span className="mt-0.5 block break-words text-xs text-muted-foreground">{a.mensagem}</span>
        {a.sugestao && (
          <span className="mt-0.5 block break-words text-xs font-medium text-primary">
            {a.sugestao}
          </span>
        )}
      </span>
    </button>
  )
}
