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
import { useSetEtapaDatas, type Etapa } from "@/features/checklist/checklistApi"

// Datas direto na ETAPA — só faz sentido quando ela não tem tarefas (senão a etapa deriva das tarefas).
export function EtapaDatasDialog({
  obraId,
  etapa,
  onOpenChange,
}: {
  obraId: string
  etapa: Etapa | null
  onOpenChange: (open: boolean) => void
}) {
  const salvar = useSetEtapaDatas(obraId)
  const [inicio, setInicio] = useState("")
  const [fim, setFim] = useState("")

  useEffect(() => {
    if (!etapa) return
    setInicio(etapa.data_inicio ?? "")
    setFim(etapa.data_fim ?? "")
  }, [etapa])

  const invalida = !!inicio && !!fim && fim < inicio

  async function onSave() {
    if (!etapa || salvar.isPending) return
    if (invalida) {
      toast.error("A data de fim não pode ser anterior à de início.")
      return
    }
    try {
      await salvar.mutateAsync({
        etapaId: etapa.id,
        data_inicio: inicio || null,
        data_fim: fim || null,
      })
      toast.success("Datas da etapa atualizadas")
      onOpenChange(false)
    } catch {
      toast.error("Não foi possível salvar.")
    }
  }

  return (
    <Dialog open={etapa !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Datas da etapa</DialogTitle>
          <DialogDescription className="truncate">{etapa?.nome}</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3">
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
