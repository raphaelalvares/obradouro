import { Building2, ChevronRight, Plus } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router-dom"

import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { CriarObraDialog } from "@/features/obras/CriarObraDialog"
import { useObras, type Obra } from "@/features/obras/obrasApi"

const dataFmt = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" })

export function ObrasPage() {
  const [criando, setCriando] = useState(false)
  const obras = useObras()

  return (
    <div className="animate-fade-up">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Suas obras</div>
          <h1 className="font-word text-4xl leading-none">OBRAS</h1>
        </div>
        <Button onClick={() => setCriando(true)}>
          <Plus />
          Nova obra
        </Button>
      </div>

      {obras.isLoading && <CenteredSpinner />}

      {obras.isError && (
        <ErrorState
          message="Não foi possível carregar suas obras."
          onRetry={() => void obras.refetch()}
        />
      )}

      {obras.isSuccess && obras.data.length === 0 && (
        <EmptyState
          icon={Building2}
          title="Nenhuma obra ainda"
          description="Crie a primeira obra para começar a organizar o cronograma e o checklist."
          action={
            <Button onClick={() => setCriando(true)}>
              <Plus />
              Criar primeira obra
            </Button>
          }
        />
      )}

      {obras.isSuccess && obras.data.length > 0 && (
        <ul className="space-y-3">
          {obras.data.map((o) => (
            <li key={o.id}>
              <ObraCard obra={o} />
            </li>
          ))}
        </ul>
      )}

      <CriarObraDialog open={criando} onOpenChange={setCriando} />
    </div>
  )
}

function ObraCard({ obra }: { obra: Obra }) {
  return (
    <Link to={`/obras/${obra.id}`} className="block">
      <Card className="flex items-center justify-between p-5 transition-colors hover:border-primary/40">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-display text-sm text-muted-foreground">
              #{obra.seq_humano ?? "—"}
            </span>
            <StatusBadge status={obra.status} />
          </div>
          <h2 className="mt-1 truncate text-base font-medium">{obra.nome}</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            criada em {dataFmt.format(new Date(obra.created_at))}
          </p>
        </div>
        <ChevronRight className="size-5 shrink-0 text-muted-foreground" />
      </Card>
    </Link>
  )
}

function StatusBadge({ status }: { status: Obra["status"] }) {
  const ativa = status === "ativa"
  return (
    <span
      className={cn(
        "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide",
        ativa
          ? "border-primary/50 text-primary"
          : "border-muted-foreground/40 text-muted-foreground",
      )}
    >
      {ativa ? "Ativa" : "Arquivada"}
    </span>
  )
}
