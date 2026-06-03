import { Building2, Check, Loader2, Unlink } from "lucide-react"
import { toast } from "sonner"

import { CenteredSpinner, EmptyState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import { useObras } from "@/features/obras/obrasApi"
import { useVincularObra } from "@/features/projetos/projetosApi"

export function VincularObraDialog({
  projetoId,
  obraIdAtual,
  open,
  onOpenChange,
}: {
  projetoId: string
  obraIdAtual: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const obras = useObras()
  const vincular = useVincularObra(projetoId)
  const lista = obras.data ?? []

  async function escolher(obraId: string | null) {
    if (vincular.isPending) return
    try {
      await vincular.mutateAsync(obraId)
      toast.success(obraId ? "Obra vinculada" : "Obra desvinculada")
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível atualizar o vínculo.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Vincular obra</DialogTitle>
          <DialogDescription>Conecte este projeto a uma obra do seu acervo.</DialogDescription>
        </DialogHeader>

        <div className="max-h-[55vh] space-y-2 overflow-y-auto">
          {obras.isLoading ? (
            <CenteredSpinner />
          ) : lista.length === 0 ? (
            <EmptyState
              icon={Building2}
              title="Nenhuma obra"
              description="Crie uma obra antes de vincular este projeto."
            />
          ) : (
            <ul className="space-y-2">
              {lista.map((o) => {
                const atual = o.id === obraIdAtual
                return (
                  <li key={o.id}>
                    <button
                      type="button"
                      disabled={vincular.isPending}
                      onClick={() => escolher(atual ? null : o.id)}
                      className={cn(
                        "flex w-full items-center justify-between rounded-xl border p-4 text-left transition-colors",
                        atual ? "border-primary/50 bg-primary/5" : "border-border hover:border-primary/40",
                      )}
                    >
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium">{o.nome}</div>
                        <div className="text-xs text-muted-foreground">#{o.seq_humano ?? "—"}</div>
                      </div>
                      {atual && <Check className="size-4 shrink-0 text-primary" />}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        {obraIdAtual && (
          <Button
            variant="outline"
            className="w-full text-destructive hover:bg-destructive/10 hover:text-destructive"
            disabled={vincular.isPending}
            onClick={() => escolher(null)}
          >
            {vincular.isPending ? <Loader2 className="animate-spin" /> : <Unlink />}
            Desvincular obra
          </Button>
        )}
      </DialogContent>
    </Dialog>
  )
}
