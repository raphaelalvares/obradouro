import { Loader2 } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import {
  useAtualizarPendencia,
  useCriarPendencia,
  type Pendencia,
  type Prioridade,
} from "@/features/acompanhamento/acompanhamentoApi"
import type { Ambiente } from "@/features/checklist/checklistApi"
import type { Equipe } from "@/features/equipes/equipesApi"

const PRIORIDADES: { v: Prioridade; label: string }[] = [
  { v: "baixa", label: "Baixa" },
  { v: "media", label: "Média" },
  { v: "alta", label: "Alta" },
]

/** Cria/edita uma pendência (punch list). entry=null → nova. */
export function PendenciaDialog({
  obraId,
  open,
  entry,
  ambientes,
  equipes,
  onOpenChange,
}: {
  obraId: string
  open: boolean
  entry: Pendencia | null
  ambientes: Ambiente[]
  equipes: Equipe[]
  onOpenChange: (open: boolean) => void
}) {
  const criar = useCriarPendencia(obraId)
  const atualizar = useAtualizarPendencia(obraId)
  const [descricao, setDescricao] = useState("")
  const [prioridade, setPrioridade] = useState<Prioridade>("media")
  const [ambienteId, setAmbienteId] = useState<string | null>(null)
  const [equipeId, setEquipeId] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setDescricao(entry?.descricao ?? "")
    setPrioridade(entry?.prioridade ?? "media")
    setAmbienteId(entry?.ambiente_id ?? null)
    setEquipeId(entry?.equipe_id ?? null)
  }, [open, entry])

  const salvando = criar.isPending || atualizar.isPending

  async function onSave() {
    if (salvando) return
    if (!descricao.trim()) {
      toast.error("Descreva a pendência.")
      return
    }
    const payload = {
      descricao: descricao.trim(),
      prioridade,
      ambiente_id: ambienteId,
      equipe_id: equipeId,
    }
    try {
      if (entry) await atualizar.mutateAsync({ id: entry.id, patch: payload })
      else await criar.mutateAsync(payload)
      toast.success(entry ? "Pendência atualizada" : "Pendência aberta")
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{entry ? "Editar pendência" : "Nova pendência"}</DialogTitle>
          <DialogDescription>O que precisa ser resolvido na obra.</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs text-muted-foreground">Descrição</span>
            <Textarea
              value={descricao}
              onChange={(e) => setDescricao(e.target.value)}
              maxLength={1000}
              rows={3}
              placeholder="Ex.: Rejunte do box mal acabado; retocar pintura do hall…"
            />
          </label>

          <div>
            <span className="mb-1 block text-xs text-muted-foreground">Prioridade</span>
            <div className="flex gap-1.5">
              {PRIORIDADES.map((p) => (
                <button
                  key={p.v}
                  type="button"
                  onClick={() => setPrioridade(p.v)}
                  className={cn(
                    "flex-1 rounded-lg border px-3 py-1.5 text-sm transition-colors",
                    prioridade === p.v
                      ? "border-primary bg-primary/10 text-foreground"
                      : "border-border text-muted-foreground hover:text-foreground",
                  )}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {ambientes.length > 0 && (
            <label className="block">
              <span className="mb-1 block text-xs text-muted-foreground">Cômodo (onde)</span>
              <select
                value={ambienteId ?? ""}
                onChange={(e) => setAmbienteId(e.target.value || null)}
                className="h-11 w-full rounded-xl border border-input bg-card px-3 text-base sm:text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                <option value="">Sem cômodo</option>
                {ambientes.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.nome}
                  </option>
                ))}
              </select>
            </label>
          )}

          {equipes.length > 0 && (
            <div>
              <span className="mb-1 block text-xs text-muted-foreground">Responsável</span>
              <div className="flex flex-wrap gap-1.5">
                <Chip selecionada={equipeId === null} onClick={() => setEquipeId(null)} label="—" />
                {equipes.map((eq) => (
                  <Chip
                    key={eq.id}
                    cor={eq.cor}
                    label={eq.nome}
                    selecionada={equipeId === eq.id}
                    onClick={() => setEquipeId(eq.id)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button className="flex-1" disabled={salvando} onClick={onSave}>
            {salvando && <Loader2 className="animate-spin" />}
            Salvar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function Chip({
  cor,
  label,
  selecionada,
  onClick,
}: {
  cor?: string
  label: string
  selecionada: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
        selecionada
          ? "border-primary bg-primary/10 text-foreground"
          : "border-border text-muted-foreground hover:text-foreground",
      )}
    >
      {cor && <span className="size-2.5 shrink-0 rounded-full" style={{ background: cor }} aria-hidden />}
      {label}
    </button>
  )
}
