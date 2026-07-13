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

/** Alvo de uma nova tarefa/subtarefa: a etapa (e opcionalmente a subetapa ou a tarefa-pai) onde
 * ela nasce. Com `parentId` o alvo é uma SUBTAREFA (filha de uma tarefa); sem ele, uma tarefa. */
export interface NovaTarefaTarget {
  etapaId: string
  subetapaId?: string
  parentId?: string // tarefa-pai → cria uma SUBTAREFA com custo (mesma folha, um nível abaixo)
  titulo: string // "em <etapa/subetapa/tarefa>" (display)
}

/** Diálogo de criar tarefa/subtarefa COM custo (metragem/MO). O quick-add inline (só nome) coexiste. */
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
  // subtarefa quando nasce sob uma tarefa-pai; senão, tarefa (só muda a palavra na copy).
  const palavra = target?.parentId ? "subtarefa" : "tarefa"

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
      toast.error(`Não foi possível criar a ${palavra}.`)
      setSalvando(false)
    }
  }

  return (
    <Dialog open={target !== null} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nova {palavra}</DialogTitle>
          <DialogDescription className="truncate">{target?.titulo}</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="nome-tarefa">Nome da {palavra}</Label>
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
              Criar {palavra}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
