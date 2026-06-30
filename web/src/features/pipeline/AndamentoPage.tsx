import { ArrowRight, Check, ChevronLeft, Loader2, Pencil } from "lucide-react"
import { useState } from "react"
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"

import { CenteredSpinner, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import {
  useAtualizarEtapa,
  useDecidirIniciarObra,
  usePipeline,
  type EtapaProjeto,
  type StatusEtapa,
} from "@/features/pipeline/pipelineApi"
import { useProjeto } from "@/features/projetos/projetosApi"

const STATUS: readonly [StatusEtapa, string][] = [
  ["a_fazer", "A fazer"],
  ["em_andamento", "Em andamento"],
  ["aguardando_cliente", "Aguardando cliente"],
  ["concluida", "Concluída"],
]
const STATUS_LABEL = Object.fromEntries(STATUS) as Record<StatusEtapa, string>

function chipClass(s: StatusEtapa): string {
  if (s === "concluida") return "border-primary/40 bg-primary/5 text-primary"
  if (s === "em_andamento") return "border-primary/40 text-primary"
  if (s === "aguardando_cliente") return "border-primary/60 bg-primary/10 text-primary"
  return "border-border text-muted-foreground"
}

function fmt(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("pt-BR")
}

export function AndamentoPage() {
  const { projetoId = "" } = useParams()
  const projeto = useProjeto(projetoId)
  const pipeline = usePipeline(projetoId)
  const ehArquiteto = projeto.data?.meu_papel === "arquiteto"
  const [iniciarOpen, setIniciarOpen] = useState(false)
  const [editando, setEditando] = useState<string | null>(null)

  return (
    <div className="animate-fade-up">
      <Link
        to={`/projetos/${projetoId}`}
        className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronLeft className="size-4" />
        Projeto
      </Link>

      <div className="mb-6">
        <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Andamento do projeto</div>
        <h1 className="font-word text-3xl leading-tight break-words">{projeto.data?.nome ?? "…"}</h1>
      </div>

      {pipeline.isLoading ? (
        <CenteredSpinner />
      ) : pipeline.isError ? (
        <ErrorState
          message="Não foi possível carregar o andamento."
          onRetry={() => void pipeline.refetch()}
        />
      ) : (
        <ol className="space-y-2">
          {pipeline.data?.etapas.map((e, i) => (
            <EtapaItem
              key={e.etapa}
              etapa={e}
              numero={i + 1}
              ehArquiteto={ehArquiteto}
              projetoId={projetoId}
              editando={editando === e.etapa}
              onEditar={() => setEditando((v) => (v === e.etapa ? null : e.etapa))}
              onIniciar={() => setIniciarOpen(true)}
            />
          ))}
        </ol>
      )}

      <IniciarObraDialog projetoId={projetoId} open={iniciarOpen} onOpenChange={setIniciarOpen} />
    </div>
  )
}

function EtapaItem({
  etapa,
  numero,
  ehArquiteto,
  projetoId,
  editando,
  onEditar,
  onIniciar,
}: {
  etapa: EtapaProjeto
  numero: number
  ehArquiteto: boolean
  projetoId: string
  editando: boolean
  onEditar: () => void
  onIniciar: () => void
}) {
  const concluida = etapa.status === "concluida"
  return (
    <li
      className={cn(
        "rounded-2xl border bg-card p-4 transition-colors",
        etapa.acao_pendente ? "border-primary/50" : "border-border",
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "flex size-8 shrink-0 items-center justify-center rounded-full border text-sm font-medium",
            concluida ? "border-primary bg-primary text-primary-foreground" : "border-border text-muted-foreground",
          )}
        >
          {concluida ? <Check className="size-4" /> : numero}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-medium">{etapa.rotulo}</h2>
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide",
                chipClass(etapa.status),
              )}
            >
              {STATUS_LABEL[etapa.status]}
            </span>
          </div>

          {etapa.etapa === "medicao" && etapa.data_prevista && (
            <p className="mt-1 text-xs text-muted-foreground">
              Medição agendada para {fmt(etapa.data_prevista)}
            </p>
          )}
          {etapa.observacao && (
            <p className="mt-1 text-xs text-muted-foreground break-words">{etapa.observacao}</p>
          )}
          {etapa.etapa === "iniciar_obra" && etapa.decisao && (
            <p className="mt-1 text-xs font-medium text-primary">
              {etapa.decisao === "sim" ? "Cliente confirmou o início da obra" : "Cliente optou por não iniciar"}
            </p>
          )}

          {/* CLIENTE: ação pendente neste gate */}
          {!ehArquiteto && etapa.acao_pendente && (
            <div className="mt-2">
              {etapa.gate === "iniciar_obra" ? (
                <Button size="sm" onClick={onIniciar}>
                  Decidir início <ArrowRight className="size-4" />
                </Button>
              ) : (
                <Button asChild size="sm">
                  <Link to={`/projetos/${projetoId}/${etapa.gate === "proposta" ? "orcamento" : "revisoes"}`}>
                    {etapa.gate === "proposta" ? "Ver proposta" : "Ver e aprovar"}
                    <ArrowRight className="size-4" />
                  </Link>
                </Button>
              )}
            </div>
          )}

          {/* ARQUITETO: avançar a etapa */}
          {ehArquiteto && (
            <div className="mt-2">
              <Button variant="ghost" size="sm" onClick={onEditar} className="h-7 px-2 text-xs">
                <Pencil className="size-3.5" />
                {editando ? "Fechar" : "Editar"}
              </Button>
              {editando && (
                <EtapaEditor projetoId={projetoId} etapa={etapa} onClose={onEditar} />
              )}
            </div>
          )}
        </div>
      </div>
    </li>
  )
}

function EtapaEditor({
  projetoId,
  etapa,
  onClose,
}: {
  projetoId: string
  etapa: EtapaProjeto
  onClose: () => void
}) {
  const [status, setStatus] = useState<StatusEtapa>(etapa.status)
  const [data, setData] = useState<string | null>(etapa.data_prevista)
  const [obs, setObs] = useState(etapa.observacao ?? "")
  const mut = useAtualizarEtapa(projetoId)

  async function salvar() {
    if (mut.isPending) return
    const obsLimpa = obs.trim()
    try {
      await mut.mutateAsync({
        etapa: etapa.etapa,
        status,
        // só envia o que faz sentido (undefined = não enviado, o backend distingue de null)
        data_prevista: etapa.etapa === "medicao" ? data || null : undefined,
        observacao: obsLimpa === (etapa.observacao ?? "") ? undefined : obsLimpa || null,
      })
      toast.success("Etapa atualizada")
      onClose()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar.")
    }
  }

  return (
    <div className="mt-3 space-y-3 rounded-xl border border-border bg-background p-3">
      <div className="space-y-1.5">
        <Label className="text-xs">Status</Label>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as StatusEtapa)}
          className="h-9 w-full rounded-lg border border-border bg-card px-3 text-sm"
        >
          {STATUS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </div>
      {etapa.etapa === "medicao" && (
        <div className="space-y-1.5">
          <Label className="text-xs">Data da medição</Label>
          <Input type="date" value={data ?? ""} onChange={(e) => setData(e.target.value || null)} />
        </div>
      )}
      <div className="space-y-1.5">
        <Label className="text-xs">Observação / link (ex.: apresentação)</Label>
        <Input
          value={obs}
          onChange={(e) => setObs(e.target.value)}
          placeholder="Opcional — visível pro cliente"
        />
      </div>
      <Button size="sm" onClick={salvar} disabled={mut.isPending}>
        {mut.isPending && <Loader2 className="animate-spin" />}
        Salvar
      </Button>
    </div>
  )
}

function IniciarObraDialog({
  projetoId,
  open,
  onOpenChange,
}: {
  projetoId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const mut = useDecidirIniciarObra(projetoId)
  async function decidir(d: "sim" | "nao") {
    if (mut.isPending) return
    try {
      await mut.mutateAsync(d)
      onOpenChange(false)
      toast.success(d === "sim" ? "Tudo certo — vamos iniciar a obra!" : "Decisão registrada")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível registrar.")
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Iniciar a obra?</DialogTitle>
          <DialogDescription>
            Você aprovou o orçamento. Confirme se quer iniciar a obra agora — o arquiteto segue com a
            abertura.
          </DialogDescription>
        </DialogHeader>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => decidir("nao")} disabled={mut.isPending}>
            Ainda não
          </Button>
          <Button onClick={() => decidir("sim")} disabled={mut.isPending}>
            {mut.isPending ? <Loader2 className="animate-spin" /> : <Check />}
            Sim, iniciar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
