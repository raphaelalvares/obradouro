import { ChevronRight, KeyRound, Plus, Sparkles, UserCheck } from "lucide-react"
import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import { CriarProjetoDialog } from "@/features/projetos/CriarProjetoDialog"
import { ResgatarCodigoDialog } from "@/features/projetos/ResgatarCodigoDialog"
import {
  useAceitarConvite,
  useProjetos,
  useProjetosPendentes,
  type Projeto,
  type ProjetoPendente,
} from "@/features/projetos/projetosApi"

const dataFmt = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" })

export function ProjetosPage() {
  const [criando, setCriando] = useState(false)
  const [resgatando, setResgatando] = useState(false)
  const projetos = useProjetos()
  const pendentes = useProjetosPendentes()
  const temPendentes = (pendentes.data?.length ?? 0) > 0

  return (
    <div className="animate-fade-up">
      <div className="mb-6 flex items-end justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Seu ateliê</div>
          <h1 className="font-word text-4xl leading-none">PROJETOS</h1>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" title="Entrar com código" onClick={() => setResgatando(true)}>
            <KeyRound />
          </Button>
          <Button onClick={() => setCriando(true)}>
            <Plus />
            Novo projeto
          </Button>
        </div>
      </div>

      {temPendentes && <PendentesSection pendentes={pendentes.data ?? []} />}

      {projetos.isLoading && <CenteredSpinner />}

      {projetos.isError && (
        <ErrorState
          message="Não foi possível carregar seus projetos."
          onRetry={() => void projetos.refetch()}
        />
      )}

      {projetos.isSuccess && projetos.data.length === 0 && !temPendentes && (
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
      <ResgatarCodigoDialog open={resgatando} onOpenChange={setResgatando} />
    </div>
  )
}

function PendentesSection({ pendentes }: { pendentes: ProjetoPendente[] }) {
  return (
    <div className="mb-6 space-y-2">
      <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Convites pendentes</div>
      <ul className="space-y-2">
        {pendentes.map((p) => (
          <li key={p.projeto_id}>
            <PendenteCard pendente={p} />
          </li>
        ))}
      </ul>
    </div>
  )
}

function PendenteCard({ pendente }: { pendente: ProjetoPendente }) {
  const aceitar = useAceitarConvite()
  const navigate = useNavigate()

  async function onAceitar() {
    try {
      await aceitar.mutateAsync(pendente.projeto_id)
      toast.success(`Você entrou em "${pendente.projeto_nome}"`)
      navigate(`/projetos/${pendente.projeto_id}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível aceitar o convite.")
    }
  }

  return (
    <Card className="flex items-center justify-between gap-3 border-primary/40 bg-primary/5 p-4">
      <div className="min-w-0">
        <h3 className="truncate text-sm font-medium">{pendente.projeto_nome}</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {pendente.invited_by_nome ? `Convidado por ${pendente.invited_by_nome}` : "Você foi convidado"}
        </p>
      </div>
      <Button size="sm" disabled={aceitar.isPending} onClick={onAceitar}>
        <UserCheck />
        Aceitar
      </Button>
    </Card>
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
          <h2 className="mt-1 truncate text-base font-medium">{projeto.nome}</h2>
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
