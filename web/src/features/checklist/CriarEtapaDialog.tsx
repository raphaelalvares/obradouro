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
import { ApiError } from "@/lib/api"
import { useCriarEtapa } from "@/features/checklist/checklistApi"

const MAX = 200

export function CriarEtapaDialog({
  obraId,
  open,
  onOpenChange,
}: {
  obraId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [nome, setNome] = useState("")
  const criar = useCriarEtapa(obraId)
  const valido = nome.trim().length > 0

  function close(o: boolean) {
    if (!o) setNome("")
    onOpenChange(o)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || criar.isPending) return
    try {
      const etapa = await criar.mutateAsync(nome)
      toast.success(`Etapa "${etapa.nome}" criada`)
      close(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível criar a etapa.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nova etapa</DialogTitle>
          <DialogDescription>Um grupo de itens do cronograma (ex.: Acabamentos).</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="nome-etapa">Nome da etapa</Label>
            <Input
              id="nome-etapa"
              autoFocus
              required
              maxLength={MAX}
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: Fundação"
            />
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => close(false)}>
              Cancelar
            </Button>
            <Button type="submit" className="flex-1" disabled={!valido || criar.isPending}>
              {criar.isPending && <Loader2 className="animate-spin" />}
              Criar etapa
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
