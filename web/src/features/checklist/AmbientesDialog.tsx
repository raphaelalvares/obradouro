import { ChevronDown, ChevronUp, Loader2, Plus, Trash2 } from "lucide-react"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/lib/api"
import {
  useAtualizarAmbiente,
  useCriarAmbiente,
  useExcluirAmbiente,
  useReordenarAmbientes,
  type Ambiente,
} from "@/features/checklist/checklistApi"

/**
 * Gestão dos cômodos da obra (registro): adicionar, renomear (propaga aos itens), área (m²),
 * reordenar e excluir (desliga dos itens, sem apagá-los). Poka-yoke: excluir pede confirmação inline.
 */
export function AmbientesDialog({
  obraId,
  ambientes,
  open,
  onOpenChange,
}: {
  obraId: string
  ambientes: Ambiente[]
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const criar = useCriarAmbiente(obraId)
  const atualizar = useAtualizarAmbiente(obraId)
  const excluir = useExcluirAmbiente(obraId)
  const reordenar = useReordenarAmbientes(obraId)

  const [novo, setNovo] = useState("")
  const [confirmando, setConfirmando] = useState<string | null>(null)

  async function adicionar(e: FormEvent) {
    e.preventDefault()
    const nome = novo.trim()
    if (!nome) return
    setNovo("")
    try {
      await criar.mutateAsync({ nome })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível adicionar.")
    }
  }

  async function renomear(a: Ambiente, nome: string) {
    const limpo = nome.trim()
    if (!limpo || limpo === a.nome) return
    try {
      await atualizar.mutateAsync({ ambId: a.id, nome: limpo })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível renomear.")
    }
  }

  async function setArea(a: Ambiente, raw: string) {
    const v = raw.trim() ? Math.max(0, Number(raw.replace(",", ".")) || 0) : null
    if (v === (a.area_m2 ?? null)) return
    try {
      await atualizar.mutateAsync({ ambId: a.id, area_m2: v })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar a área.")
    }
  }

  async function mover(idx: number, dir: -1 | 1) {
    const alvo = idx + dir
    if (alvo < 0 || alvo >= ambientes.length) return
    const ids = ambientes.map((a) => a.id)
    ;[ids[idx], ids[alvo]] = [ids[alvo], ids[idx]]
    try {
      await reordenar.mutateAsync(ids)
    } catch {
      toast.error("Não foi possível reordenar.")
    }
  }

  async function remover(a: Ambiente) {
    setConfirmando(null)
    try {
      await excluir.mutateAsync(a.id)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível excluir.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Cômodos da obra</DialogTitle>
          <DialogDescription>
            Organize os ambientes (Cozinha, Suíte, Área externa…). Renomear aqui atualiza em todas as
            tarefas; excluir só desliga o cômodo das tarefas (não apaga nada).
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {ambientes.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
              Nenhum cômodo ainda. Adicione abaixo (ou eles aparecem ao marcar o cômodo de uma tarefa).
            </p>
          ) : (
            <ul className="max-h-[50vh] space-y-1.5 overflow-y-auto">
              {ambientes.map((a, idx) => (
                // key inclui nome/área: força remount dos inputs (uncontrolled) quando o servidor
                // canoniza/normaliza o valor, evitando o input ficar "stale" com o que foi digitado.
                <li
                  key={`${a.id}:${a.nome}:${a.area_m2 ?? ""}`}
                  className="flex items-center gap-2 rounded-lg border border-border p-2"
                >
                  <div className="flex shrink-0 flex-col">
                    <button
                      type="button"
                      aria-label="Subir"
                      disabled={idx === 0 || reordenar.isPending}
                      onClick={() => void mover(idx, -1)}
                      className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30"
                    >
                      <ChevronUp className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      aria-label="Descer"
                      disabled={idx === ambientes.length - 1 || reordenar.isPending}
                      onClick={() => void mover(idx, 1)}
                      className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-30"
                    >
                      <ChevronDown className="size-3.5" />
                    </button>
                  </div>
                  <Input
                    defaultValue={a.nome}
                    maxLength={120}
                    aria-label="Nome do cômodo"
                    onBlur={(e) => void renomear(a, e.target.value)}
                    className="h-9 min-w-0 flex-1"
                  />
                  <div className="flex shrink-0 items-center gap-1">
                    <Input
                      defaultValue={a.area_m2 != null ? String(a.area_m2).replace(".", ",") : ""}
                      inputMode="decimal"
                      aria-label="Área em m²"
                      placeholder="m²"
                      onBlur={(e) => void setArea(a, e.target.value)}
                      className="h-9 w-16 text-center"
                    />
                    <span className="text-[11px] text-muted-foreground">m²</span>
                  </div>
                  {confirmando === a.id ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="destructive"
                      disabled={excluir.isPending}
                      onClick={() => void remover(a)}
                    >
                      {excluir.isPending ? <Loader2 className="animate-spin" /> : "Excluir"}
                    </Button>
                  ) : (
                    <button
                      type="button"
                      aria-label="Excluir cômodo"
                      onClick={() => setConfirmando(a.id)}
                      className="shrink-0 rounded-md p-1.5 text-muted-foreground transition-colors hover:text-destructive"
                    >
                      <Trash2 className="size-4" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}

          <form onSubmit={adicionar} className="flex items-center gap-2 border-t border-border pt-3">
            <Input
              value={novo}
              onChange={(e) => setNovo(e.target.value)}
              maxLength={120}
              placeholder="Novo cômodo…"
              className="min-w-0 flex-1"
            />
            <Button type="submit" disabled={!novo.trim() || criar.isPending} className="shrink-0">
              {criar.isPending ? <Loader2 className="animate-spin" /> : <Plus />}
              Adicionar
            </Button>
          </form>
        </div>
      </DialogContent>
    </Dialog>
  )
}
