import { Loader2, PackageCheck, Undo2 } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ApiError } from "@/lib/api"
import { useMarcarEntrega } from "@/features/obras/obrasApi"

function fmt(iso: string): string {
  return new Date(iso).toLocaleDateString("pt-BR")
}

/** Marco de ENTREGA da obra (arquiteto). Marcar entregue ENCERRA os acessos de cliente que valem
 * "até a entrega" (poka-yoke: confirma antes). Desfazer reabre. */
export function EntregaObraDialog({
  obraId,
  entregueEm,
  open,
  onOpenChange,
}: {
  obraId: string
  entregueEm: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const marcar = useMarcarEntrega(obraId)
  const entregue = Boolean(entregueEm)

  async function acao(v: boolean) {
    if (marcar.isPending) return
    try {
      await marcar.mutateAsync(v)
      onOpenChange(false)
      toast.success(v ? "Obra marcada como entregue" : "Entrega desfeita")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível atualizar.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{entregue ? "Entrega da obra" : "Marcar obra como entregue"}</DialogTitle>
          <DialogDescription>
            {entregue
              ? `Entregue em ${fmt(entregueEm as string)}. Desfazer reabre os acessos "até a entrega".`
              : 'Isso encerra os acessos de cliente que valem "até a entrega da obra". Você pode desfazer depois.'}
          </DialogDescription>
        </DialogHeader>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          {entregue ? (
            <Button variant="outline" onClick={() => acao(false)} disabled={marcar.isPending}>
              {marcar.isPending ? <Loader2 className="animate-spin" /> : <Undo2 />}
              Desfazer entrega
            </Button>
          ) : (
            <Button onClick={() => acao(true)} disabled={marcar.isPending}>
              {marcar.isPending ? <Loader2 className="animate-spin" /> : <PackageCheck />}
              Marcar entregue
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
