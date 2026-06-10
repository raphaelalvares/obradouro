import { Loader2 } from "lucide-react"
import { useEffect, useRef, useState, type FormEvent } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Combobox } from "@/components/ui/combobox"
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

/** subtotal = round(unit × qtd, 2) → string mascarada "R$ x.xxx,xx". */
function subtotalMasc(unit: number, qtd: number): string {
  return maskValorBRL(String(Math.round(unit * qtd * 100)))
}

/** Reescala um custo (string mascarada) por um fator → string mascarada. Quantidade é multiplicador.
 * Campo VAZIO continua vazio (não materializa "R$ 0,00" ao escalar). */
function escalaValor(masked: string, fator: number): string {
  const atual = parseValor(masked)
  if (atual == null) return ""
  return maskValorBRL(String(Math.round(atual * fator * 100)))
}

function qtdNum(s: string): number {
  return Number(s.replace(",", ".")) || 0
}

/** Quantidade: só dígitos + UMA vírgula (decimal BR). Bloqueia o ponto (que a máscara de moeda usa
 * como milhar) — senão "1.234" viraria 1,234 e furaria a escala e o valor salvo. */
function limpaQtd(s: string): string {
  const so = s.replace(/[^\d,]/g, "")
  const i = so.indexOf(",")
  return i < 0 ? so : so.slice(0, i + 1) + so.slice(i + 1).replace(/,/g, "")
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
  // quantidade é MULTIPLICADOR: ao mudar, os custos escalam proporcionalmente (newQ/prevQ). prevQty
  // guarda a qtd de referência (do item ao abrir, ou a definida ao puxar do catálogo).
  // SNAPSHOT no foco da quantidade: {qtd, custos} no instante em que o campo ganha foco. A cada tecla
  // escalamos os custos a partir DESSE snapshot (não encadeado) → digitar "50" não passa por "5×",
  // verba (qtd 0) nunca escala, e o estado já fica certo mesmo se submeter com Enter sem dar blur.
  const baseQtd = useRef<{ q: number; mo: string; material: string; equip: string } | null>(null)

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
    baseQtd.current = null
  }, [open, item, etapaPadrao, ambientePadrao])

  /** Puxa um serviço do catálogo: preenche descrição/unidade/etapa e calcula custos = unit × qtd. */
  function puxarDoCatalogo(servicoId: string) {
    const s = catalogo.data?.find((x) => x.id === servicoId)
    if (!s) return
    const q = qtdNum(quantidade) || 1
    setDescricao(s.descricao)
    if (s.unidade) setUnidade(s.unidade)
    if (!etapa.trim() && s.etapa_sugerida) setEtapa(s.etapa_sugerida)
    if (qtdNum(quantidade) <= 0) setQuantidade("1")
    baseQtd.current = null
    setMo(subtotalMasc(s.custo_mo, q))
    setMaterial(subtotalMasc(s.custo_material, q))
    setEquip(subtotalMasc(s.custo_equipamento, q))
  }

  function onQtdChange(valor: string) {
    const limpo = limpaQtd(valor)
    setQuantidade(limpo)
    const base = baseQtd.current
    const novaQ = qtdNum(limpo)
    // escala a partir do snapshot do foco; só com base e nova qtd > 0 (qtd vazia/0 não mexe nos custos).
    if (base && base.q > 0 && novaQ > 0) {
      const fator = novaQ / base.q
      setMo(escalaValor(base.mo, fator))
      setMaterial(escalaValor(base.material, fator))
      setEquip(escalaValor(base.equip, fator))
    }
  }

  const subtotal = (parseValor(mo) ?? 0) + (parseValor(material) ?? 0) + (parseValor(equip) ?? 0)
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
          <DialogDescription>
            Custos por linha (M.O / material / equipamento). Mudar a quantidade reajusta os custos
            proporcionalmente.
          </DialogDescription>
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

          <div className="space-y-1.5">
            <Label htmlFor="orc-ambiente">Cômodo</Label>
            <Combobox
              id="orc-ambiente"
              value={ambiente}
              onChange={setAmbiente}
              options={ambientesExistentes}
              placeholder="Ex.: Banheiro suíte (vazio = obra geral)"
              emptyHint="Nenhum cômodo neste orçamento ainda."
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
                onFocus={() => {
                  baseQtd.current = { q: qtdNum(quantidade), mo, material, equip }
                }}
                onChange={(e) => onQtdChange(e.target.value)}
                onBlur={() => {
                  baseQtd.current = null
                }}
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

          <div className="flex items-center justify-between rounded-xl border border-border bg-card px-4 py-2.5">
            <span className="text-sm text-muted-foreground">Subtotal da linha</span>
            <span className="font-display text-base tabular-nums">{formatBRL(subtotal)}</span>
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
