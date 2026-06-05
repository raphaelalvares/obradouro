import { Loader2 } from "lucide-react"
import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router-dom"
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
import { useCriarProjeto } from "@/features/projetos/projetosApi"

const MAX = 200

export function CriarProjetoDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [nome, setNome] = useState("")
  const [revisoes, setRevisoes] = useState("")
  const criar = useCriarProjeto()
  const navigate = useNavigate()
  const valido = nome.trim().length > 0

  function close(o: boolean) {
    if (!o) {
      setNome("")
      setRevisoes("")
    }
    onOpenChange(o)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || criar.isPending) return
    const incl = revisoes.trim() === "" ? null : Math.max(0, Math.floor(Number(revisoes)))
    try {
      const proj = await criar.mutateAsync({ nome, revisoes_incluidas: incl })
      toast.success(`Projeto "${proj.nome}" criado`)
      close(false)
      navigate(`/projetos/${proj.id}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível criar o projeto.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Novo projeto</DialogTitle>
          <DialogDescription>
            Onboarding, moodboard e ciclo de revisões com o cliente.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="nome-projeto">Nome do projeto</Label>
            <Input
              id="nome-projeto"
              required
              maxLength={MAX}
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: Apartamento Jardins"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rev-incluidas">Alterações incluídas (opcional)</Label>
            <Input
              id="rev-incluidas"
              type="number"
              inputMode="numeric"
              min={0}
              value={revisoes}
              onChange={(e) => setRevisoes(e.target.value)}
              placeholder="Ex.: 3"
            />
            <p className="text-xs text-muted-foreground">
              Quantas alterações entram no contrato. Em branco = não controlar (o sistema nunca
              sinaliza).
            </p>
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => close(false)}>
              Cancelar
            </Button>
            <Button type="submit" className="flex-1" disabled={!valido || criar.isPending}>
              {criar.isPending && <Loader2 className="animate-spin" />}
              Criar projeto
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
