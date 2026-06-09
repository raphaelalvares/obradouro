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
import { maskValorBRL, parseValor } from "@/features/comercial/format"
import {
  useAddItem,
  useEditItem,
  type ItemForm,
  type OrcItem,
} from "@/features/orcamento/orcamentosApi"

function valorInicial(n: number | null | undefined): string {
  return n ? maskValorBRL(String(Math.round(n * 100))) : ""
}

export function ItemDialog({
  open,
  onOpenChange,
  projetoId,
  versaoId,
  item,
  etapaPadrao,
  etapasExistentes,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projetoId: string
  versaoId: string
  /** presente = edição */
  item?: OrcItem | null
  /** ao adicionar dentro de um grupo, pré-preenche a etapa */
  etapaPadrao?: string
  etapasExistentes: string[]
}) {
  const editando = !!item
  const add = useAddItem(projetoId, versaoId)
  const editar = useEditItem(projetoId, versaoId)
  const salvando = add.isPending || editar.isPending

  const [etapa, setEtapa] = useState("")
  const [descricao, setDescricao] = useState("")
  const [unidade, setUnidade] = useState("")
  const [quantidade, setQuantidade] = useState("")
  const [mo, setMo] = useState("")
  const [material, setMaterial] = useState("")
  const [equip, setEquip] = useState("")

  useEffect(() => {
    if (!open) return
    setEtapa(item?.etapa ?? etapaPadrao ?? "")
    setDescricao(item?.descricao ?? "")
    setUnidade(item?.unidade ?? "")
    setQuantidade(item?.quantidade != null ? String(item.quantidade).replace(".", ",") : "")
    setMo(valorInicial(item?.valor_mo))
    setMaterial(valorInicial(item?.valor_material))
    setEquip(valorInicial(item?.valor_equipamento))
  }, [open, item, etapaPadrao])

  const valido = etapa.trim().length > 0 && descricao.trim().length > 0

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || salvando) return
    const payload: ItemForm = {
      etapa: etapa.trim(),
      descricao: descricao.trim(),
      unidade: unidade.trim() || null,
      quantidade: quantidade.trim() ? Number(quantidade.replace(",", ".")) || null : null,
      valor_mo: parseValor(mo) ?? 0,
      valor_material: parseValor(material) ?? 0,
      valor_equipamento: parseValor(equip) ?? 0,
    }
    try {
      if (editando && item) {
        await editar.mutateAsync({ itemId: item.id, patch: payload })
      } else {
        await add.mutateAsync(payload)
      }
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar o serviço.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{editando ? "Editar serviço" : "Novo serviço"}</DialogTitle>
          <DialogDescription>Custos por linha, separados em M.O / material / equipamento.</DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <datalist id="orc-etapas">
            {etapasExistentes.map((e) => (
              <option key={e} value={e} />
            ))}
          </datalist>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="orc-etapa">Etapa *</Label>
              <Input
                id="orc-etapa"
                list="orc-etapas"
                value={etapa}
                onChange={(e) => setEtapa(e.target.value)}
                placeholder="Ex.: Alvenaria"
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="orc-desc">Serviço *</Label>
              <Input
                id="orc-desc"
                value={descricao}
                onChange={(e) => setDescricao(e.target.value)}
                placeholder="Ex.: Parede bloco cerâmico"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="orc-un">Unidade</Label>
              <Input
                id="orc-un"
                value={unidade}
                onChange={(e) => setUnidade(e.target.value)}
                placeholder="m², un, vb…"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="orc-qtd">Quantidade</Label>
              <Input
                id="orc-qtd"
                inputMode="decimal"
                value={quantidade}
                onChange={(e) => setQuantidade(e.target.value)}
                placeholder="0"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="orc-mo">Mão de obra</Label>
              <Input id="orc-mo" inputMode="numeric" value={mo} onChange={(e) => setMo(maskValorBRL(e.target.value))} placeholder="R$ 0,00" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="orc-mat">Material</Label>
              <Input id="orc-mat" inputMode="numeric" value={material} onChange={(e) => setMaterial(maskValorBRL(e.target.value))} placeholder="R$ 0,00" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="orc-eq">Equipamento</Label>
              <Input id="orc-eq" inputMode="numeric" value={equip} onChange={(e) => setEquip(maskValorBRL(e.target.value))} placeholder="R$ 0,00" />
            </div>
          </div>

          <div className="flex gap-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" className="flex-1" disabled={!valido || salvando}>
              {salvando && <Loader2 className="animate-spin" />}
              {editando ? "Salvar" : "Adicionar"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
