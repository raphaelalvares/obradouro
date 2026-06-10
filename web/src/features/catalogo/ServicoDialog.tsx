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
  useAtualizarServico,
  useCriarServico,
  type ServicoCatalogo,
} from "@/features/catalogo/catalogoApi"

function valorInicial(n: number | null | undefined): string {
  return n ? maskValorBRL(String(Math.round(n * 100))) : ""
}

export function ServicoDialog({
  open,
  onOpenChange,
  servico,
  etapasSugeridas,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** presente = edição */
  servico?: ServicoCatalogo | null
  etapasSugeridas: string[]
}) {
  const editando = !!servico
  const criar = useCriarServico()
  const atualizar = useAtualizarServico()
  const salvando = criar.isPending || atualizar.isPending

  const [descricao, setDescricao] = useState("")
  const [unidade, setUnidade] = useState("")
  const [etapa, setEtapa] = useState("")
  const [mo, setMo] = useState("")
  const [material, setMaterial] = useState("")
  const [equip, setEquip] = useState("")

  useEffect(() => {
    if (!open) return
    setDescricao(servico?.descricao ?? "")
    setUnidade(servico?.unidade ?? "")
    setEtapa(servico?.etapa_sugerida ?? "")
    setMo(valorInicial(servico?.custo_mo))
    setMaterial(valorInicial(servico?.custo_material))
    setEquip(valorInicial(servico?.custo_equipamento))
  }, [open, servico])

  const valido = descricao.trim().length > 0

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || salvando) return
    const form = {
      descricao: descricao.trim(),
      unidade: unidade.trim() || null,
      etapa_sugerida: etapa.trim() || null,
      custo_mo: parseValor(mo) ?? 0,
      custo_material: parseValor(material) ?? 0,
      custo_equipamento: parseValor(equip) ?? 0,
    }
    try {
      if (editando && servico) {
        await atualizar.mutateAsync({ id: servico.id, patch: form })
      } else {
        await criar.mutateAsync(form)
      }
      onOpenChange(false)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast.error("Já existe um serviço com esse nome no catálogo.")
      } else {
        toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar.")
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{editando ? "Editar serviço" : "Novo serviço"}</DialogTitle>
          <DialogDescription>
            Custo de referência <strong>por unidade</strong> (R$/un). Ao usar num orçamento, multiplica
            pela quantidade.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <datalist id="cat-etapas">
            {etapasSugeridas.map((e) => (
              <option key={e} value={e} />
            ))}
          </datalist>

          <div className="space-y-1.5">
            <Label htmlFor="cat-desc">Serviço *</Label>
            <Input
              id="cat-desc"
              value={descricao}
              onChange={(e) => setDescricao(e.target.value)}
              placeholder="Ex.: Porcelanato em parede"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="cat-un">Unidade</Label>
              <Input
                id="cat-un"
                value={unidade}
                onChange={(e) => setUnidade(e.target.value)}
                placeholder="m², un, vb…"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cat-etapa">Etapa sugerida</Label>
              <Input
                id="cat-etapa"
                list="cat-etapas"
                value={etapa}
                onChange={(e) => setEtapa(e.target.value)}
                placeholder="Ex.: Revestimentos"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="cat-mo">Mão de obra / un</Label>
              <Input id="cat-mo" inputMode="numeric" value={mo} onChange={(e) => setMo(maskValorBRL(e.target.value))} placeholder="R$ 0,00" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cat-mat">Material / un</Label>
              <Input id="cat-mat" inputMode="numeric" value={material} onChange={(e) => setMaterial(maskValorBRL(e.target.value))} placeholder="R$ 0,00" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cat-eq">Equipamento / un</Label>
              <Input id="cat-eq" inputMode="numeric" value={equip} onChange={(e) => setEquip(maskValorBRL(e.target.value))} placeholder="R$ 0,00" />
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
