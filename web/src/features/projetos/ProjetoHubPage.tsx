import {
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  GitPullRequestArrow,
  LayoutGrid,
  Link2,
  Users,
  type LucideIcon,
} from "lucide-react"
import { useState } from "react"
import { Link, useParams } from "react-router-dom"

import { CenteredSpinner, ErrorState } from "@/components/feedback/states"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { BriefingDialog } from "@/features/projetos/BriefingDialog"
import { PessoasDialog } from "@/features/projetos/PessoasDialog"
import { VincularObraDialog } from "@/features/projetos/VincularObraDialog"
import { useContador, useProjeto } from "@/features/projetos/projetosApi"

export function ProjetoHubPage() {
  const { projetoId = "" } = useParams()
  const projeto = useProjeto(projetoId)
  const contador = useContador(projetoId)
  const [briefingOpen, setBriefingOpen] = useState(false)
  const [pessoasOpen, setPessoasOpen] = useState(false)
  const [vincularOpen, setVincularOpen] = useState(false)

  const ehArquiteto = projeto.data?.meu_papel === "arquiteto"

  // resumo do contador p/ a tarjeta de revisões
  let revLegenda = "Entregas e decisões do cliente"
  if (contador.data?.controla) {
    const c = contador.data
    revLegenda =
      c.alem_count > 0
        ? `${c.alem_count} além do incluído · ${c.usadas}/${c.incluidas}`
        : `${c.usadas}/${c.incluidas} alterações usadas`
  }

  return (
    <div className="animate-fade-up">
      <Link
        to="/projetos"
        className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronLeft className="size-4" />
        Projetos
      </Link>

      <div className="mb-6">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-primary">
          <span>Projeto #{projeto.data?.seq_humano ?? "—"}</span>
          {projeto.data?.meu_papel && (
            <span className="text-muted-foreground">
              · {ehArquiteto ? "Arquiteto" : "Cliente"}
            </span>
          )}
        </div>
        <h1 className="truncate font-word text-3xl leading-tight">{projeto.data?.nome ?? "…"}</h1>
      </div>

      {projeto.isLoading ? (
        <CenteredSpinner />
      ) : projeto.isError ? (
        <ErrorState
          message="Não foi possível carregar o projeto."
          onRetry={() => void projeto.refetch()}
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3">
            <ModuloCard
              icon={ClipboardList}
              title="Onboarding"
              desc="Briefing do projeto"
              onClick={() => setBriefingOpen(true)}
            />
            <ModuloCard icon={LayoutGrid} title="Moodboard" desc="Referências visuais" to="moodboard" />
            <ModuloCard
              icon={GitPullRequestArrow}
              title="Revisões"
              desc={revLegenda}
              to="revisoes"
              highlight={(contador.data?.alem_count ?? 0) > 0}
            />
            {ehArquiteto && (
              <ModuloCard
                icon={Users}
                title="Pessoas"
                desc="Convidar o cliente"
                onClick={() => setPessoasOpen(true)}
              />
            )}
          </div>

          {/* Vínculo com a obra (só arquiteto) */}
          {ehArquiteto && (
            <button
              type="button"
              onClick={() => setVincularOpen(true)}
              className="mt-3 flex w-full items-center justify-between rounded-2xl border border-border bg-card p-4 text-left transition-colors hover:border-primary/40"
            >
              <div className="flex items-center gap-3">
                <div className="flex size-9 items-center justify-center rounded-lg bg-accent text-primary">
                  <Link2 className="size-4" />
                </div>
                <div>
                  <div className="text-sm font-medium">Obra vinculada</div>
                  <div className="text-xs text-muted-foreground">
                    {projeto.data?.obra_id ? "Conectado a uma obra" : "Nenhuma obra ligada"}
                  </div>
                </div>
              </div>
              <ChevronRight className="size-4 text-muted-foreground" />
            </button>
          )}
        </>
      )}

      <BriefingDialog
        projetoId={projetoId}
        open={briefingOpen}
        onOpenChange={setBriefingOpen}
        podeEditar={ehArquiteto}
      />
      {ehArquiteto && (
        <>
          <PessoasDialog projetoId={projetoId} open={pessoasOpen} onOpenChange={setPessoasOpen} />
          <VincularObraDialog
            projetoId={projetoId}
            obraIdAtual={projeto.data?.obra_id ?? null}
            open={vincularOpen}
            onOpenChange={setVincularOpen}
          />
        </>
      )}
    </div>
  )
}

interface ModuloCardProps {
  icon: LucideIcon
  title: string
  desc: string
  to?: string
  onClick?: () => void
  highlight?: boolean
}

function ModuloCard({ icon: Icon, title, desc, to, onClick, highlight }: ModuloCardProps) {
  const inner = (
    <Card
      className={cn(
        "flex h-full flex-col gap-3 p-5 transition-colors hover:border-primary/40",
        highlight && "border-primary/50 bg-primary/5",
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex size-11 items-center justify-center rounded-xl bg-accent text-primary">
          <Icon className="size-5" />
        </div>
        <ChevronRight className="size-4 text-muted-foreground" />
      </div>
      <div>
        <h2 className="text-base font-medium">{title}</h2>
        <p className="line-clamp-2 text-xs text-muted-foreground">{desc}</p>
      </div>
    </Card>
  )

  if (to) {
    return (
      <Link to={to} className="block">
        {inner}
      </Link>
    )
  }
  return (
    <button type="button" onClick={onClick} className="block w-full text-left">
      {inner}
    </button>
  )
}
