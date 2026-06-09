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
import { Textarea } from "@/components/ui/textarea"
import { ApiError } from "@/lib/api"
import { useAtualizarParams, type OrcVersao, type ParamsPatch } from "@/features/orcamento/orcamentosApi"

const pct = (n: number) => (n ? String(n).replace(".", ",") : "")
const numPct = (s: string) => (s.trim() ? Number(s.replace(",", ".")) || 0 : 0)

export function ParamsDialog({
  open,
  onOpenChange,
  projetoId,
  versao,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projetoId: string
  versao: OrcVersao
}) {
  const salvar = useAtualizarParams(projetoId, versao.id)
  const [data, setData] = useState("")
  const [validade, setValidade] = useState("")
  const [majMo, setMajMo] = useState("")
  const [majMat, setMajMat] = useState("")
  const [majEq, setMajEq] = useState("")
  const [bdi, setBdi] = useState("")
  const [imposto, setImposto] = useState("")
  const [obs, setObs] = useState("")

  useEffect(() => {
    if (!open) return
    setData(versao.data ?? "")
    setValidade(versao.validade ?? "")
    setMajMo(pct(versao.maj_mo))
    setMajMat(pct(versao.maj_material))
    setMajEq(pct(versao.maj_equipamento))
    setBdi(pct(versao.bdi))
    setImposto(pct(versao.imposto))
    setObs(versao.observacoes ?? "")
  }, [open, versao])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (salvar.isPending) return
    const patch: ParamsPatch = {
      data: data || null,
      validade: validade || null,
      maj_mo: numPct(majMo),
      maj_material: numPct(majMat),
      maj_equipamento: numPct(majEq),
      bdi: numPct(bdi),
      imposto: numPct(imposto),
      observacoes: obs.trim() || null,
    }
    try {
      await salvar.mutateAsync(patch)
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Parâmetros do orçamento</DialogTitle>
          <DialogDescription>
            Datas e percentuais (majoração por tipo, BDI, imposto). Pode ajustar tudo depois, quando
            quiser — nada aqui é definitivo.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="p-data">Data</Label>
              <Input id="p-data" type="date" value={data} onChange={(e) => setData(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="p-val">Validade</Label>
              <Input id="p-val" type="date" value={validade} onChange={(e) => setValidade(e.target.value)} />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Majoração por tipo (%)</Label>
            <div className="grid grid-cols-3 gap-2">
              <PctInput aria="Majoração mão de obra" value={majMo} onChange={setMajMo} hint="M.O" />
              <PctInput aria="Majoração material" value={majMat} onChange={setMajMat} hint="Material" />
              <PctInput aria="Majoração equipamento" value={majEq} onChange={setMajEq} hint="Equip." />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="p-bdi">BDI (%)</Label>
              <Input id="p-bdi" inputMode="decimal" value={bdi} onChange={(e) => setBdi(e.target.value)} placeholder="0" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="p-imp">Imposto (%)</Label>
              <Input id="p-imp" inputMode="decimal" value={imposto} onChange={(e) => setImposto(e.target.value)} placeholder="0" />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="p-obs">Observações / condições</Label>
            <Textarea id="p-obs" value={obs} onChange={(e) => setObs(e.target.value)} placeholder="Condições de pagamento, escopo…" />
          </div>

          <div className="flex gap-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" className="flex-1" disabled={salvar.isPending}>
              {salvar.isPending && <Loader2 className="animate-spin" />}
              Salvar
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function PctInput({
  aria,
  value,
  onChange,
  hint,
}: {
  aria: string
  value: string
  onChange: (v: string) => void
  hint: string
}) {
  return (
    <div>
      <Input aria-label={aria} inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)} placeholder="0" />
      <p className="mt-1 text-center text-[10px] uppercase tracking-wide text-muted-foreground">{hint}</p>
    </div>
  )
}
