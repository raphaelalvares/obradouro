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
import { cn } from "@/lib/utils"
import { ApiError } from "@/lib/api"
import { formatBRL, maskValorBRL, parseValor } from "@/features/comercial/format"
import { useCatalogo } from "@/features/catalogo/catalogoApi"
import {
  useAddItem,
  useEditItem,
  type ItemForm,
  type OrcItem,
} from "@/features/orcamento/orcamentosApi"

function valorInicial(n: number | null | undefined): string {
  return n ? maskValorBRL(String(Math.round(n * 100))) : ""
}

/** Custo unitário (R$/un) vindo do catálogo, p/ recalcular o subtotal quando a quantidade muda. */
interface UnitLink {
  mo: number
  material: number
  equipamento: number
}

/** subtotal = round(unit × qtd, 2) → string mascarada "R$ x.xxx,xx". Espelha a matemática do backend. */
function subtotalMasc(unit: number, qtd: number): string {
  return maskValorBRL(String(Math.round(unit * qtd * 100)))
}

function qtdNum(s: string): number {
  return Number(s.replace(",", ".")) || 0
}

export function ItemDialog({
  open,
  onOpenChange,
  projetoId,
  versaoId,
  item,
  etapaPadrao,
  ambientePadrao,
  etapasExistentes,
  ambientesExistentes,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projetoId: string
  versaoId: string
  /** presente = edição */
  item?: OrcItem | null
  /** ao adicionar dentro de um grupo, pré-preenche a etapa */
  etapaPadrao?: string
  /** ao adicionar dentro de um cômodo (vista por cômodo), pré-preenche o ambiente */
  ambientePadrao?: string
  etapasExistentes: string[]
  ambientesExistentes: string[]
}) {
  const editando = !!item
  const add = useAddItem(projetoId, versaoId)
  const editar = useEditItem(projetoId, versaoId)
  const salvando = add.isPending || editar.isPending
  const catalogo = useCatalogo(open) // só busca quando o dialog abre

  const [etapa, setEtapa] = useState("")
  const [ambiente, setAmbiente] = useState("")
  const [descricao, setDescricao] = useState("")
  const [unidade, setUnidade] = useState("")
  const [quantidade, setQuantidade] = useState("")
  const [mo, setMo] = useState("")
  const [material, setMaterial] = useState("")
  const [equip, setEquip] = useState("")
  // quando puxado do catálogo, guardamos o custo unitário p/ recalcular ao mudar a quantidade.
  // editar um custo à mão DESLIGA o vínculo (o valor manual manda).
  const [link, setLink] = useState<UnitLink | null>(null)

  useEffect(() => {
    if (!open) return
    setEtapa(item?.etapa ?? etapaPadrao ?? "")
    setAmbiente(item?.ambiente ?? ambientePadrao ?? "")
    setDescricao(item?.descricao ?? "")
    setUnidade(item?.unidade ?? "")
    setQuantidade(item?.quantidade != null ? String(item.quantidade).replace(".", ",") : "")
    setMo(valorInicial(item?.valor_mo))
    setMaterial(valorInicial(item?.valor_material))
    setEquip(valorInicial(item?.valor_equipamento))
    setLink(null)
  }, [open, item, etapaPadrao, ambientePadrao])

  /** Aplica um serviço do catálogo: preenche descrição/unidade/etapa e calcula custos = unit × qtd. */
  function puxarDoCatalogo(servicoId: string) {
    const s = catalogo.data?.find((x) => x.id === servicoId)
    if (!s) return
    const q = qtdNum(quantidade) || 1
    setDescricao(s.descricao)
    if (s.unidade) setUnidade(s.unidade)
    if (!etapa.trim() && s.etapa_sugerida) setEtapa(s.etapa_sugerida)
    if (qtdNum(quantidade) <= 0) setQuantidade("1")
    const u: UnitLink = { mo: s.custo_mo, material: s.custo_material, equipamento: s.custo_equipamento }
    setLink(u)
    setMo(subtotalMasc(u.mo, q))
    setMaterial(subtotalMasc(u.material, q))
    setEquip(subtotalMasc(u.equipamento, q))
  }

  function onQtdChange(valor: string) {
    setQuantidade(valor)
    // só recalcula com qtd > 0 — apagar o campo p/ redigitar NÃO deve zerar os custos no meio do caminho.
    if (link && qtdNum(valor) > 0) {
      const q = qtdNum(valor)
      setMo(subtotalMasc(link.mo, q))
      setMaterial(subtotalMasc(link.material, q))
      setEquip(subtotalMasc(link.equipamento, q))
    }
  }

  const valido = etapa.trim().length > 0 && descricao.trim().length > 0

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || salvando) return
    const payload: ItemForm = {
      etapa: etapa.trim(),
      ambiente: ambiente.trim() || null,
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

          {(catalogo.data?.length ?? 0) > 0 && (
            <div className="space-y-1.5 rounded-xl border border-dashed border-border p-3">
              <Label htmlFor="orc-cat">Puxar do catálogo (opcional)</Label>
              <select
                id="orc-cat"
                value=""
                onChange={(e) => {
                  if (e.target.value) puxarDoCatalogo(e.target.value)
                  e.target.value = ""
                }}
                className={cn(
                  "flex h-11 w-full min-w-0 rounded-xl border border-input bg-card px-4 py-2 text-base sm:text-sm",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                )}
              >
                <option value="">Escolher um serviço de referência…</option>
                {catalogo.data!.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.descricao}
                    {s.unidade ? ` · ${s.unidade}` : ""} ·{" "}
                    {formatBRL(s.custo_mo + s.custo_material + s.custo_equipamento)}/un
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">
                Preenche o serviço e calcula os custos pela quantidade. Você pode ajustar tudo depois.
              </p>
            </div>
          )}

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

          <datalist id="orc-ambientes">
            {ambientesExistentes.map((a) => (
              <option key={a} value={a} />
            ))}
          </datalist>
          <div className="space-y-1.5">
            <Label htmlFor="orc-ambiente">Cômodo</Label>
            <Input
              id="orc-ambiente"
              list="orc-ambientes"
              value={ambiente}
              onChange={(e) => setAmbiente(e.target.value)}
              placeholder="Ex.: Banheiro suíte (vazio = obra geral)"
            />
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
                onChange={(e) => onQtdChange(e.target.value)}
                placeholder="0"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="orc-mo">Mão de obra</Label>
              <Input id="orc-mo" inputMode="numeric" value={mo} onChange={(e) => { setMo(maskValorBRL(e.target.value)); setLink(null) }} placeholder="R$ 0,00" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="orc-mat">Material</Label>
              <Input id="orc-mat" inputMode="numeric" value={material} onChange={(e) => { setMaterial(maskValorBRL(e.target.value)); setLink(null) }} placeholder="R$ 0,00" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="orc-eq">Equipamento</Label>
              <Input id="orc-eq" inputMode="numeric" value={equip} onChange={(e) => { setEquip(maskValorBRL(e.target.value)); setLink(null) }} placeholder="R$ 0,00" />
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
