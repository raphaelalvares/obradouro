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
import { useResgatarCodigo } from "@/features/projetos/projetosApi"

export function ResgatarCodigoDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [codigo, setCodigo] = useState("")
  const resgatar = useResgatarCodigo()
  const navigate = useNavigate()
  const valido = codigo.trim().length >= 6

  function close(o: boolean) {
    if (!o) setCodigo("")
    onOpenChange(o)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || resgatar.isPending) return
    try {
      const res = await resgatar.mutateAsync(codigo)
      close(false)
      if (res.estado === "ativo") {
        toast.success("Você já participa deste projeto")
        navigate(`/projetos/${res.projeto_id}`)
      } else {
        toast.success("Convite recebido — aceite para entrar no projeto")
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Código inválido ou expirado.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Entrar com código</DialogTitle>
          <DialogDescription>
            Digite o código que o arquiteto compartilhou para entrar no projeto.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="codigo-projeto">Código</Label>
            <Input
              id="codigo-projeto"
              required
              value={codigo}
              onChange={(e) => setCodigo(e.target.value.toUpperCase())}
              placeholder="Ex.: K7M2PQ9X"
              className="font-display tracking-[0.2em]"
            />
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => close(false)}>
              Cancelar
            </Button>
            <Button type="submit" className="flex-1" disabled={!valido || resgatar.isPending}>
              {resgatar.isPending && <Loader2 className="animate-spin" />}
              Entrar
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
