import {
  Camera,
  CheckCircle2,
  ChevronLeft,
  ClipboardList,
  HardHat,
  Pencil,
  Plus,
  RotateCcw,
  Trash2,
} from "lucide-react"
import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"

import { useAuth } from "@/auth/AuthProvider"
import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { cn } from "@/lib/utils"
import { ApiError } from "@/lib/api"
import { FotosDialog, type FotosTarget } from "@/features/anexos/FotosDialog"
import { formatBRL, formatData } from "@/features/comercial/format"
import { useChecklist } from "@/features/checklist/checklistApi"
import { useEquipes } from "@/features/equipes/equipesApi"
import { useObra } from "@/features/obras/obrasApi"
import { FuncoesDialog } from "@/features/funcoes/FuncoesDialog"
import { CurvaSChart } from "@/features/acompanhamento/CurvaSChart"
import { DiarioDialog } from "@/features/acompanhamento/DiarioDialog"
import { PendenciaDialog } from "@/features/acompanhamento/PendenciaDialog"
import {
  useAvanco,
  useDiario,
  useExcluirDiario,
  useExcluirPendencia,
  usePendencias,
  useAtualizarPendencia,
  type Diario,
  type Pendencia,
  type Prioridade,
} from "@/features/acompanhamento/acompanhamentoApi"

type Aba = "diario" | "pendencias" | "avanco"

export function AcompanhamentoPage() {
  const { obraId = "" } = useParams()
  const obra = useObra(obraId)
  const { user } = useAuth()
  const [aba, setAba] = useState<Aba>("diario")
  const [fotos, setFotos] = useState<FotosTarget | null>(null)
  const qc = useQueryClient()

  const papel = obra.data?.meu_papel
  const ehArquiteto = papel === "arquiteto"
  const ehExecutor = papel === "arquiteto" || papel === "prestador"

  // ao fechar as fotos, refaz a lista do alvo p/ o contador (n_fotos) refletir o que mudou.
  function onFotosClose() {
    if (fotos?.parentType === "diario") void qc.invalidateQueries({ queryKey: ["diario", obraId] })
    if (fotos?.parentType === "pendencia")
      void qc.invalidateQueries({ queryKey: ["pendencias", obraId] })
    // foto de tarefa-do-diário: refaz as medições (n_fotos por tarefa) — qualquer diário da obra.
    if (fotos?.parentType === "diario_tarefa")
      void qc.invalidateQueries({ queryKey: ["diario-tarefas", obraId] })
    setFotos(null)
  }

  return (
    <div className="animate-fade-up">
      <Link
        to={`/obras/${obraId}`}
        className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronLeft className="size-4" />
        {obra.data?.nome ?? "Obra"}
      </Link>

      <div className="mb-5">
        <div className="text-[10px] uppercase tracking-[0.3em] text-primary">
          Obra #{obra.data?.seq_humano ?? "—"}
        </div>
        <h1 className="font-word text-3xl leading-tight">Acompanhamento</h1>
      </div>

      <div className="mb-4 inline-flex rounded-lg border border-border p-0.5 text-sm">
        {(
          [
            ["diario", "Diário"],
            ["pendencias", "Pendências"],
            ["avanco", "Avanço"],
          ] as const
        ).map(([v, label]) => (
          <button
            key={v}
            type="button"
            onClick={() => setAba(v)}
            className={cn(
              "rounded-md px-3 py-1 font-medium transition-colors",
              aba === v ? "bg-primary text-primary-foreground" : "text-muted-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {aba === "diario" && (
        <DiarioTab
          obraId={obraId}
          ehExecutor={ehExecutor}
          ehArquiteto={ehArquiteto}
          userId={user?.id}
          onFotos={setFotos}
        />
      )}
      {aba === "pendencias" && (
        <PendenciasTab
          obraId={obraId}
          ehExecutor={ehExecutor}
          ehArquiteto={ehArquiteto}
          userId={user?.id}
          onFotos={setFotos}
        />
      )}
      {aba === "avanco" && <AvancoTab obraId={obraId} />}

      <FotosDialog
        obraId={obraId}
        target={fotos}
        readOnly={!ehExecutor}
        onOpenChange={(o) => !o && onFotosClose()}
      />
    </div>
  )
}

// ============================ Diário ============================
function DiarioTab({
  obraId,
  ehExecutor,
  ehArquiteto,
  userId,
  onFotos,
}: {
  obraId: string
  ehExecutor: boolean
  ehArquiteto: boolean
  userId?: string
  onFotos: (t: FotosTarget) => void
}) {
  const diario = useDiario(obraId)
  const excluir = useExcluirDiario(obraId)
  const [dialog, setDialog] = useState<{ entry: Diario | null } | null>(null)
  const [apagar, setApagar] = useState<Diario | null>(null)
  const [funcoesOpen, setFuncoesOpen] = useState(false)

  const podeEditar = (d: Diario) => ehArquiteto || (!!userId && d.created_by === userId)

  async function onApagar() {
    if (!apagar) return
    try {
      await excluir.mutateAsync(apagar.id)
      toast.success("Entrada removida")
      setApagar(null)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível excluir.")
    }
  }

  const lista = diario.data ?? []

  return (
    <div className="space-y-3">
      {(ehArquiteto || ehExecutor) && (
        <div className="flex flex-wrap items-center justify-between gap-2">
          {ehArquiteto ? (
            <Button variant="outline" size="sm" onClick={() => setFuncoesOpen(true)}>
              <HardHat />
              Funções
            </Button>
          ) : (
            <span />
          )}
          {ehExecutor && (
            <Button onClick={() => setDialog({ entry: null })}>
              <Plus />
              Nova entrada
            </Button>
          )}
        </div>
      )}

      {diario.isLoading && <CenteredSpinner />}
      {diario.isError && (
        <ErrorState message="Não foi possível carregar o diário." onRetry={() => void diario.refetch()} />
      )}
      {diario.isSuccess && lista.length === 0 && (
        <EmptyState
          icon={ClipboardList}
          title="Diário vazio"
          description="Registre o que acontece na obra no dia a dia (serviços, clima, ocorrências)."
        />
      )}

      {lista.map((d) => (
        <Card key={d.id} className="p-4">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
                <span className="font-display text-foreground">{formatData(d.data)}</span>
                {d.clima && <span>· {d.clima}</span>}
                {d.efetivo != null && <span>· {d.efetivo} pessoa(s)</span>}
                {d.autor_nome && <span>· {d.autor_nome}</span>}
              </div>
              {d.texto && (
                <p className="mt-1 whitespace-pre-wrap break-words text-sm">{d.texto}</p>
              )}
              {d.efetivo_itens.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {d.efetivo_itens.map((it) => (
                    <span
                      key={it.funcao_id}
                      className="rounded-full bg-accent px-2 py-0.5 text-[11px] text-muted-foreground"
                    >
                      {it.nome} · {it.qtd}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="flex shrink-0 items-center">
              {podeEditar(d) && (
                <>
                  <IconBtn label="Editar" onClick={() => setDialog({ entry: d })}>
                    <Pencil className="size-4" />
                  </IconBtn>
                  <IconBtn label="Excluir" danger onClick={() => setApagar(d)}>
                    <Trash2 className="size-4" />
                  </IconBtn>
                </>
              )}
            </div>
          </div>
          {(ehExecutor || d.n_fotos > 0) && (
            <button
              type="button"
              onClick={() =>
                onFotos({ parentType: "diario", parentId: d.id, titulo: formatData(d.data) })
              }
              className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-muted-foreground transition-colors hover:text-primary"
            >
              <Camera className="size-3.5" />
              {d.n_fotos > 0 ? `${d.n_fotos} foto(s)` : "Adicionar foto"}
            </button>
          )}
        </Card>
      ))}

      <DiarioDialog
        obraId={obraId}
        open={dialog !== null}
        entry={dialog?.entry ?? null}
        podeGerenciar={ehArquiteto}
        podeEditar={dialog?.entry ? podeEditar(dialog.entry) : ehExecutor}
        onFotos={onFotos}
        onOpenChange={(o) => !o && setDialog(null)}
      />
      {ehArquiteto && <FuncoesDialog open={funcoesOpen} onOpenChange={setFuncoesOpen} />}
      <ConfirmDialog
        open={apagar !== null}
        onOpenChange={(o) => !o && setApagar(null)}
        title="Excluir entrada?"
        description={<>O registro de {apagar ? formatData(apagar.data) : ""} será removido.</>}
        pending={excluir.isPending}
        onConfirm={onApagar}
      />
    </div>
  )
}

// ============================ Pendências ============================
const PRIO_COR: Record<Prioridade, string> = {
  alta: "text-destructive",
  media: "text-primary",
  baixa: "text-muted-foreground",
}
const PRIO_LABEL: Record<Prioridade, string> = { alta: "Alta", media: "Média", baixa: "Baixa" }

function PendenciasTab({
  obraId,
  ehExecutor,
  ehArquiteto,
  userId,
  onFotos,
}: {
  obraId: string
  ehExecutor: boolean
  ehArquiteto: boolean
  userId?: string
  onFotos: (t: FotosTarget) => void
}) {
  const pend = usePendencias(obraId)
  const tree = useChecklist(obraId)
  const equipes = useEquipes()
  const atualizar = useAtualizarPendencia(obraId)
  const excluir = useExcluirPendencia(obraId)

  const [dialog, setDialog] = useState<{ entry: Pendencia | null } | null>(null)
  const [apagar, setApagar] = useState<Pendencia | null>(null)
  const [filtro, setFiltro] = useState<"todas" | "aberta" | "resolvida">("todas")

  const ambientes = tree.data?.ambientes ?? []
  const ambNome = new Map(ambientes.map((a) => [a.id, a.nome] as const))
  const eqMap = new Map((equipes.data ?? []).map((e) => [e.id, e] as const))

  async function resolver(p: Pendencia) {
    try {
      await atualizar.mutateAsync({
        id: p.id,
        patch: { status: p.status === "resolvida" ? "aberta" : "resolvida" },
      })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível atualizar.")
    }
  }

  async function onApagar() {
    if (!apagar) return
    try {
      await excluir.mutateAsync(apagar.id)
      toast.success("Pendência removida")
      setApagar(null)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível excluir.")
    }
  }

  const podeApagar = (p: Pendencia) => ehArquiteto || (!!userId && p.created_by === userId)
  const todas = pend.data ?? []
  const lista = filtro === "todas" ? todas : todas.filter((p) => p.status === filtro)
  const abertas = todas.filter((p) => p.status === "aberta").length

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap gap-1.5">
          {(
            [
              ["todas", "Todas"],
              ["aberta", "Abertas"],
              ["resolvida", "Resolvidas"],
            ] as const
          ).map(([v, label]) => (
            <button
              key={v}
              type="button"
              onClick={() => setFiltro(v)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs transition-colors",
                filtro === v
                  ? "border-primary bg-primary/10 text-foreground"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {label}
              {v === "aberta" && abertas > 0 ? ` · ${abertas}` : ""}
            </button>
          ))}
        </div>
        {ehExecutor && (
          <Button onClick={() => setDialog({ entry: null })}>
            <Plus />
            Nova pendência
          </Button>
        )}
      </div>

      {pend.isLoading && <CenteredSpinner />}
      {pend.isError && (
        <ErrorState message="Não foi possível carregar as pendências." onRetry={() => void pend.refetch()} />
      )}
      {pend.isSuccess && lista.length === 0 && (
        <EmptyState
          icon={CheckCircle2}
          title={filtro === "todas" ? "Nenhuma pendência" : "Nada neste filtro"}
          description="Registre defeitos e itens a resolver (punch list) para acompanhar o que falta."
        />
      )}

      {lista.map((p) => {
        const eq = p.equipe_id ? eqMap.get(p.equipe_id) : undefined
        const resolvida = p.status === "resolvida"
        return (
          <Card key={p.id} className={cn("p-4", resolvida && "opacity-70")}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className={cn("break-words text-sm font-medium", resolvida && "line-through")}>
                  {p.descricao}
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted-foreground">
                  <span className={PRIO_COR[p.prioridade]}>{PRIO_LABEL[p.prioridade]}</span>
                  {p.ambiente_id && ambNome.get(p.ambiente_id) && (
                    <span>· {ambNome.get(p.ambiente_id)}</span>
                  )}
                  {eq && (
                    <span className="inline-flex items-center gap-1">
                      ·
                      <span className="size-2 rounded-full" style={{ background: eq.cor }} aria-hidden />
                      {eq.nome}
                    </span>
                  )}
                  {resolvida && p.resolvido_por_nome && <span>· resolvida por {p.resolvido_por_nome}</span>}
                </div>
              </div>
              <div className="flex shrink-0 items-center">
                {ehExecutor && (
                  <IconBtn
                    label={resolvida ? "Reabrir" : "Marcar resolvida"}
                    onClick={() => void resolver(p)}
                  >
                    {resolvida ? <RotateCcw className="size-4" /> : <CheckCircle2 className="size-4" />}
                  </IconBtn>
                )}
                {ehArquiteto && (
                  <IconBtn label="Editar" onClick={() => setDialog({ entry: p })}>
                    <Pencil className="size-4" />
                  </IconBtn>
                )}
                {podeApagar(p) && (
                  <IconBtn label="Excluir" danger onClick={() => setApagar(p)}>
                    <Trash2 className="size-4" />
                  </IconBtn>
                )}
              </div>
            </div>
            {(ehExecutor || p.n_fotos > 0) && (
              <button
                type="button"
                onClick={() =>
                  onFotos({ parentType: "pendencia", parentId: p.id, titulo: p.descricao })
                }
                className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-muted-foreground transition-colors hover:text-primary"
              >
                <Camera className="size-3.5" />
                {p.n_fotos > 0 ? `${p.n_fotos} foto(s)` : "Adicionar foto"}
              </button>
            )}
          </Card>
        )
      })}

      <PendenciaDialog
        obraId={obraId}
        open={dialog !== null}
        entry={dialog?.entry ?? null}
        ambientes={ambientes}
        equipes={equipes.data ?? []}
        onOpenChange={(o) => !o && setDialog(null)}
      />
      <ConfirmDialog
        open={apagar !== null}
        onOpenChange={(o) => !o && setApagar(null)}
        title="Excluir pendência?"
        description={<>"{apagar?.descricao}" será removida.</>}
        pending={excluir.isPending}
        onConfirm={onApagar}
      />
    </div>
  )
}

// ============================ Avanço / curva S ============================
function AvancoTab({ obraId }: { obraId: string }) {
  const avanco = useAvanco(obraId)
  const a = avanco.data

  return (
    <div className="space-y-4">
      {avanco.isLoading && <CenteredSpinner />}
      {avanco.isError && (
        <ErrorState message="Não foi possível carregar o avanço." onRetry={() => void avanco.refetch()} />
      )}
      {a && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Card className="p-4">
              <div className="text-[11px] text-muted-foreground">Avanço real</div>
              <div className="mt-1 font-display text-2xl text-primary">{a.real_pct}%</div>
            </Card>
            <Card className="p-4">
              <div className="text-[11px] text-muted-foreground">Planejado até hoje</div>
              <div className="mt-1 font-display text-2xl">{a.planejado_pct}%</div>
            </Card>
            <Card className="col-span-2 p-4 sm:col-span-1">
              <div className="text-[11px] text-muted-foreground">Situação</div>
              <div
                className={cn(
                  "mt-1 font-display text-2xl",
                  a.real_pct + 0.05 >= a.planejado_pct ? "text-[#5FB87A]" : "text-destructive",
                )}
              >
                {a.real_pct >= a.planejado_pct ? "Em dia" : `${(a.planejado_pct - a.real_pct).toFixed(1)}% atrás`}
              </div>
            </Card>
          </div>

          <Card className="p-4">
            <div className="mb-1 flex items-center justify-between">
              <h2 className="text-sm font-medium">Curva S</h2>
              <span className="text-[11px] text-muted-foreground">
                {a.por_custo ? `Por custo · ${formatBRL(a.peso_total)}` : `Por tarefas · ${a.peso_total}`}
              </span>
            </div>
            <CurvaSChart avanco={a} />
          </Card>
        </>
      )}
    </div>
  )
}

// ============================ util ============================
function IconBtn({
  label,
  danger,
  onClick,
  children,
}: {
  label: string
  danger?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={cn(
        "rounded-lg p-2 text-muted-foreground transition-colors",
        danger ? "hover:bg-destructive/10 hover:text-destructive" : "hover:bg-accent hover:text-primary",
      )}
    >
      {children}
    </button>
  )
}
