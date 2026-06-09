import { FolderKanban, Loader2 } from "lucide-react"
import { toast } from "sonner"

import { CenteredSpinner, EmptyState } from "@/components/feedback/states"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ApiError } from "@/lib/api"
import { useVincularProjeto, type Oportunidade } from "@/features/comercial/comercialApi"
import { useProjetos } from "@/features/projetos/projetosApi"

export function VincularProjetoDialog({
  open,
  onOpenChange,
  oportunidade,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  oportunidade: Oportunidade | null
}) {
  const projetos = useProjetos()
  const vincular = useVincularProjeto()

  if (!oportunidade) return null
  const op = oportunidade

  async function escolher(projetoId: string) {
    if (vincular.isPending) return
    try {
      await vincular.mutateAsync({ opId: op.id, projetoId })
      toast.success("Projeto vinculado")
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível vincular.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Vincular projeto</DialogTitle>
          <DialogDescription>Escolha um projeto do seu acervo para ligar a este lead.</DialogDescription>
        </DialogHeader>

        <div className="-mx-1 max-h-[60vh] space-y-2 overflow-y-auto px-1">
          {projetos.isLoading && <CenteredSpinner />}
          {projetos.isSuccess && projetos.data.length === 0 && (
            <EmptyState
              icon={FolderKanban}
              title="Nenhum projeto ainda"
              description="Use 'Criar projeto' para gerar um novo a partir deste lead."
            />
          )}
          {projetos.data?.map((p) => (
            <button
              key={p.id}
              type="button"
              disabled={vincular.isPending}
              onClick={() => escolher(p.id)}
              className="flex w-full items-center gap-3 rounded-xl border border-border bg-card p-3 text-left transition-colors hover:border-primary/40 disabled:opacity-50"
            >
              <span className="shrink-0 font-display text-xs text-muted-foreground">
                #{p.seq_humano ?? "—"}
              </span>
              <span className="min-w-0 flex-1 break-words text-sm font-medium">{p.nome}</span>
              {p.obra_id && (
                <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground">
                  c/ obra
                </span>
              )}
              {vincular.isPending && <Loader2 className="size-4 shrink-0 animate-spin" />}
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
