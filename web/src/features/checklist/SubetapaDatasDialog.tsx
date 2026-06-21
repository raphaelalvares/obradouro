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
import { Input } from "@/components/ui/input"
import { useSetSubetapaDatas, type SubetapaTree } from "@/features/checklist/checklistApi"

// Datas direto na SUBETAPA — só faz sentido quando ela não tem tarefas (senão deriva das tarefas).
export function SubetapaDatasDialog({
  obraId,
  subetapa,
  onOpenChange,
}: {
  obraId: string
  subetapa: SubetapaTree | null
  onOpenChange: (open: boolean) => void
}) {
  const salvar = useSetSubetapaDatas(obraId)
  const [inicio, setInicio] = useState("")
  const [fim, setFim] = useState("")

  useEffect(() => {
    if (!subetapa) return
    setInicio(subetapa.data_inicio ?? "")
    setFim(subetapa.data_fim ?? "")
  }, [subetapa])

  const invalida = !!inicio && !!fim && fim < inicio

  async function onSave() {
    if (!subetapa || salvar.isPending) return
    if (invalida) {
      toast.error("A data de fim não pode ser anterior à de início.")
      return
    }
    try {
      await salvar.mutateAsync({
        subetapaId: subetapa.id,
        data_inicio: inicio || null,
        data_fim: fim || null,
      })
      toast.success("Datas da subetapa atualizadas")
      onOpenChange(false)
    } catch {
      toast.error("Não foi possível salvar.")
    }
  }

  return (
    <Dialog open={subetapa !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Datas da subetapa</DialogTitle>
          <DialogDescription className="truncate">{subetapa?.nome}</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-xs text-muted-foreground">Início</span>
            <Input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-muted-foreground">Fim</span>
            <Input
              type="date"
              value={fim}
              min={inicio || undefined}
              onChange={(e) => setFim(e.target.value)}
            />
          </label>
        </div>
        {invalida && (
          <p className="text-xs text-destructive">A data de fim não pode ser anterior à de início.</p>
        )}

        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button className="flex-1" disabled={salvar.isPending || invalida} onClick={onSave}>
            {salvar.isPending && <Loader2 className="animate-spin" />}
            Salvar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
