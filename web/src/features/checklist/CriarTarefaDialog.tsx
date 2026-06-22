import { Loader2 } from "lucide-react"
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
import { Label } from "@/components/ui/label"
import {
  CamposCusto,
  camposCustoToForm,
  custoVazio,
  temCusto,
  type CamposCustoValue,
} from "@/features/checklist/CamposCusto"
import type { CustoForm } from "@/features/checklist/checklistApi"

/** Alvo de uma nova tarefa: a etapa (e opcionalmente a subetapa) onde ela nasce. */
export interface NovaTarefaTarget {
  etapaId: string
  subetapaId?: string
  titulo: string // "em <etapa/subetapa>" (display)
}

/** Diálogo de criar tarefa COM custo (metragem/MO). O quick-add inline (só nome) coexiste. */
export function CriarTarefaDialog({
  target,
  onOpenChange,
  onCriar,
}: {
  target: NovaTarefaTarget | null
  onOpenChange: (open: boolean) => void
  onCriar: (nome: string, custo: CustoForm) => Promise<void>
}) {
  const [nome, setNome] = useState("")
  const [custo, setCusto] = useState<CamposCustoValue>(custoVazio)
  const [salvando, setSalvando] = useState(false)
  const valido = nome.trim().length > 0

  function close(o: boolean) {
    if (!o) {
      setNome("")
      setCusto(custoVazio)
      setSalvando(false)
    }
    onOpenChange(o)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || salvando) return
    setSalvando(true)
    try {
      await onCriar(nome.trim(), temCusto(custo) ? camposCustoToForm(custo) : {})
      close(false)
    } catch {
      toast.error("Não foi possível criar a tarefa.")
      setSalvando(false)
    }
  }

  return (
    <Dialog open={target !== null} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nova tarefa</DialogTitle>
          <DialogDescription className="truncate">{target?.titulo}</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="nome-tarefa">Nome da tarefa</Label>
            <Input
              id="nome-tarefa"
              required
              maxLength={300}
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: Assentar piso"
            />
          </div>
          <CamposCusto value={custo} onChange={setCusto} />
          <div className="flex gap-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => close(false)}>
              Cancelar
            </Button>
            <Button type="submit" className="flex-1" disabled={!valido || salvando}>
              {salvando && <Loader2 className="animate-spin" />}
              Criar tarefa
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
