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
import { useCriarObra } from "@/features/obras/obrasApi"

const MAX = 200

export function CriarObraDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [nome, setNome] = useState("")
  const criar = useCriarObra()
  const valido = nome.trim().length > 0

  function close(o: boolean) {
    if (!o) setNome("")
    onOpenChange(o)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || criar.isPending) return
    try {
      const obra = await criar.mutateAsync(nome)
      toast.success(`Obra "${obra.nome}" criada · #${obra.seq_humano ?? "—"}`)
      close(false)
    } catch (err) {
      if (err instanceof ApiError && err.isUpgrade) {
        // soft-limit: vira CTA de upgrade, não erro cru (Fase 2 — limite de obras ativas)
        toast.error(err.problem?.detail ?? "Limite do plano atingido.", {
          description: "Faça upgrade para criar mais obras ativas.",
        })
      } else if (err instanceof ApiError) {
        toast.error(err.message)
      } else {
        toast.error("Não foi possível criar a obra.")
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nova obra</DialogTitle>
          <DialogDescription>
            Dê um nome — o número da obra é atribuído automaticamente.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="nome-obra">Nome da obra</Label>
            <Input
              id="nome-obra"
              autoFocus
              required
              maxLength={MAX}
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Ex.: Reforma Apto 302"
            />
            <p className="text-right text-[11px] text-muted-foreground">
              {nome.length}/{MAX}
            </p>
          </div>

          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              className="flex-1"
              onClick={() => close(false)}
            >
              Cancelar
            </Button>
            <Button type="submit" className="flex-1" disabled={!valido || criar.isPending}>
              {criar.isPending && <Loader2 className="animate-spin" />}
              Criar obra
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
