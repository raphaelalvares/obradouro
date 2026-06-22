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
import { ApiError } from "@/lib/api"
import {
  CamposCusto,
  camposCustoDe,
  camposCustoToForm,
  custoVazio,
  type CamposCustoValue,
} from "@/features/checklist/CamposCusto"
import {
  useAtualizarEtapaDetalhes,
  useAtualizarSubetapaDetalhes,
} from "@/features/checklist/checklistApi"

/** Custo de uma ETAPA/SUBETAPA que é FOLHA (sem subitens). Espelha o ItemDetalhesDialog, mas só custo
 * (a etapa/subetapa não têm cômodo/equipe). Se ela ganhar filhos, o custo desce (move-down). */
export interface NodeCustoTarget {
  kind: "etapa" | "subetapa"
  id: string
  nome: string
  unidade: string | null
  quantidade: number | null
  valor_unitario: number | null
  mao_obra_unitaria: number | null
  custo_total: number | null
}

export function NodeDetalhesDialog({
  obraId,
  target,
  onOpenChange,
}: {
  obraId: string
  target: NodeCustoTarget | null
  onOpenChange: (open: boolean) => void
}) {
  const salvarEtapa = useAtualizarEtapaDetalhes(obraId)
  const salvarSubetapa = useAtualizarSubetapaDetalhes(obraId)
  const [custo, setCusto] = useState<CamposCustoValue>(custoVazio)

  useEffect(() => {
    if (target) setCusto(camposCustoDe(target))
  }, [target])

  const salvando = salvarEtapa.isPending || salvarSubetapa.isPending

  async function onSave() {
    if (!target || salvando) return
    const patch = camposCustoToForm(custo)
    try {
      if (target.kind === "etapa") {
        await salvarEtapa.mutateAsync({ etapaId: target.id, patch })
      } else {
        await salvarSubetapa.mutateAsync({ subetapaId: target.id, patch })
      }
      toast.success("Custo atualizado")
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar o custo.")
    }
  }

  return (
    <Dialog open={target !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Custo {target?.kind === "etapa" ? "da etapa" : "da subetapa"}</DialogTitle>
          <DialogDescription className="truncate">{target?.nome}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <CamposCusto value={custo} onChange={setCusto} />
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
