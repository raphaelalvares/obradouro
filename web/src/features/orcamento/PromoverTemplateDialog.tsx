import { Loader2 } from "lucide-react"
import { useEffect, useState, type FormEvent } from "react"
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
import { usePromoverTemplate } from "@/features/catalogo/templatesApi"
import { type OrcItem } from "@/features/orcamento/orcamentosApi"

export function PromoverTemplateDialog({
  open,
  onOpenChange,
  ambienteNome,
  itens,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  ambienteNome: string
  itens: OrcItem[]
}) {
  const promover = usePromoverTemplate()
  const [tipo, setTipo] = useState("")
  const [nivel, setNivel] = useState("")
  const [area, setArea] = useState("")

  useEffect(() => {
    if (!open) return
    setTipo(ambienteNome)
    setNivel("")
    setArea("")
  }, [open, ambienteNome])

  const valido = tipo.trim().length > 0 && nivel.trim().length > 0 && itens.length > 0

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || promover.isPending) return
    try {
      await promover.mutateAsync({
        tipo: tipo.trim(),
        nivel: nivel.trim(),
        area_referencia: area.trim() ? Number(area.replace(",", ".")) || null : null,
        itens: itens.map((i) => ({
          descricao: i.descricao,
          unidade: i.unidade,
          quantidade: i.quantidade,
          valor_mo: i.valor_mo,
          valor_material: i.valor_material,
          valor_equipamento: i.valor_equipamento,
          etapa: i.etapa,
        })),
      })
      toast.success("Cômodo salvo como template no livro")
      onOpenChange(false)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast.error("Já existe um template com esse tipo e nível.")
      } else {
        toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar o template.")
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Salvar cômodo como template</DialogTitle>
          <DialogDescription>
            Guarda os {itens.length} {itens.length === 1 ? "serviço" : "serviços"} deste cômodo no livro
            (cada um vira referência no catálogo). Entram como quantidade fixa — depois você marca no
            template quais escalam por m².
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="pt-tipo">Tipo *</Label>
              <Input
                id="pt-tipo"
                value={tipo}
                onChange={(e) => setTipo(e.target.value)}
                placeholder="Ex.: Banheiro"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pt-nivel">Nível *</Label>
              <Input
                id="pt-nivel"
                value={nivel}
                onChange={(e) => setNivel(e.target.value)}
                placeholder="Ex.: Alto padrão"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pt-area">Área de referência (m²)</Label>
            <Input
              id="pt-area"
              inputMode="decimal"
              value={area}
              onChange={(e) => setArea(e.target.value)}
              placeholder="Opcional — ex.: 20"
            />
          </div>

          <div className="flex gap-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" className="flex-1" disabled={!valido || promover.isPending}>
              {promover.isPending && <Loader2 className="animate-spin" />}
              Salvar no livro
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
