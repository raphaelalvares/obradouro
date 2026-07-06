import { ChevronRight, Plus, Sparkles } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router-dom"

import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { CriarProjetoDialog } from "@/features/projetos/CriarProjetoDialog"
import { useProjetos, type Projeto } from "@/features/projetos/projetosApi"

const dataFmt = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" })

export function ProjetosPage() {
  const [criando, setCriando] = useState(false)
  const projetos = useProjetos()

  return (
    <div className="animate-fade-up">
      <div className="mb-6 flex items-end justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Seu ateliê</div>
          <h1 className="font-word text-4xl leading-none">PROJETOS</h1>
        </div>
        <Button onClick={() => setCriando(true)}>
          <Plus />
          Novo projeto
        </Button>
      </div>

      {projetos.isLoading && <CenteredSpinner />}

      {projetos.isError && (
        <ErrorState
          message="Não foi possível carregar seus projetos."
          onRetry={() => void projetos.refetch()}
        />
      )}

      {projetos.isSuccess && projetos.data.length === 0 && (
        <EmptyState
          icon={Sparkles}
          title="Nenhum projeto ainda"
          description="Crie um projeto para iniciar o onboarding, montar o moodboard e abrir o ciclo de revisões com o cliente."
          action={
            <Button onClick={() => setCriando(true)}>
              <Plus />
              Criar primeiro projeto
            </Button>
          }
        />
      )}

      {projetos.isSuccess && projetos.data.length > 0 && (
        <ul className="space-y-3">
          {projetos.data.map((p) => (
            <li key={p.id}>
              <ProjetoCard projeto={p} />
            </li>
          ))}
        </ul>
      )}

      <CriarProjetoDialog open={criando} onOpenChange={setCriando} />
    </div>
  )
}

function ProjetoCard({ projeto }: { projeto: Projeto }) {
  const ehArquiteto = projeto.meu_papel === "arquiteto"
  return (
    <Link to={`/projetos/${projeto.id}`} className="block">
      <Card className="flex items-center justify-between p-5 transition-colors hover:border-primary/40">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-display text-sm text-muted-foreground">
              #{projeto.seq_humano ?? "—"}
            </span>
            <PapelBadge arquiteto={ehArquiteto} />
            {projeto.obra_id && (
              <span className="rounded-full border border-border px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                Obra vinculada
              </span>
            )}
          </div>
          <h2 className="mt-1 text-base font-medium break-words">{projeto.nome}</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            criado em {dataFmt.format(new Date(projeto.created_at))}
          </p>
        </div>
        <ChevronRight className="size-5 shrink-0 text-muted-foreground" />
      </Card>
    </Link>
  )
}

function PapelBadge({ arquiteto }: { arquiteto: boolean }) {
  return (
    <span
      className={cn(
        "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide",
        arquiteto ? "border-primary/50 text-primary" : "border-muted-foreground/40 text-muted-foreground",
      )}
    >
      {arquiteto ? "Arquiteto" : "Cliente"}
    </span>
  )
}
