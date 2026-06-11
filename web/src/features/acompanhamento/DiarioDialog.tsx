import { Loader2 } from "lucide-react"
import { useEffect, useState } from "react"
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
import { Textarea } from "@/components/ui/textarea"
import { ApiError } from "@/lib/api"
import { hojeISO } from "@/features/comercial/format"
import {
  useAtualizarDiario,
  useCriarDiario,
  type Diario,
} from "@/features/acompanhamento/acompanhamentoApi"

const CLIMAS = ["Ensolarado", "Nublado", "Chuva", "Garoa", "Vento forte"]

/** Cria/edita uma entrada do diário de obra. entry=null → nova entrada. */
export function DiarioDialog({
  obraId,
  open,
  entry,
  onOpenChange,
}: {
  obraId: string
  open: boolean
  entry: Diario | null
  onOpenChange: (open: boolean) => void
}) {
  const criar = useCriarDiario(obraId)
  const atualizar = useAtualizarDiario(obraId)
  const [data, setData] = useState("")
  const [texto, setTexto] = useState("")
  const [clima, setClima] = useState("")
  const [efetivo, setEfetivo] = useState("")

  useEffect(() => {
    if (!open) return
    setData(entry?.data ?? hojeISO())
    setTexto(entry?.texto ?? "")
    setClima(entry?.clima ?? "")
    setEfetivo(entry?.efetivo != null ? String(entry.efetivo) : "")
  }, [open, entry])

  const salvando = criar.isPending || atualizar.isPending

  async function onSave() {
    if (salvando) return
    if (!texto.trim()) {
      toast.error("Escreva o relato do dia.")
      return
    }
    const ef = efetivo.trim() ? Math.max(0, Math.round(Number(efetivo)) || 0) : null
    const payload = { data, texto: texto.trim(), clima: clima.trim() || null, efetivo: ef }
    try {
      if (entry) await atualizar.mutateAsync({ id: entry.id, patch: payload })
      else await criar.mutateAsync(payload)
      toast.success(entry ? "Entrada atualizada" : "Entrada registrada")
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{entry ? "Editar entrada" : "Nova entrada do diário"}</DialogTitle>
          <DialogDescription>O que aconteceu na obra neste dia.</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-muted-foreground">Data</span>
              <Input type="date" value={data} onChange={(e) => setData(e.target.value)} />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-muted-foreground">Efetivo (pessoas)</span>
              <Input
                value={efetivo}
                onChange={(e) => setEfetivo(e.target.value)}
                inputMode="numeric"
                placeholder="—"
              />
            </label>
          </div>
          <label className="block">
            <span className="mb-1 block text-xs text-muted-foreground">Clima</span>
            <Input
              value={clima}
              onChange={(e) => setClima(e.target.value)}
              maxLength={60}
              list="diario-climas"
              placeholder="Ex.: Ensolarado, Chuva…"
            />
            <datalist id="diario-climas">
              {CLIMAS.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </label>
          <label className="block">
            <span className="mb-1 block text-xs text-muted-foreground">Relato</span>
            <Textarea
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              maxLength={4000}
              rows={5}
              placeholder="Serviços executados, ocorrências, entregas, decisões…"
            />
          </label>
        </div>

        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button className="flex-1" disabled={salvando} onClick={onSave}>
            {salvando && <Loader2 className="animate-spin" />}
            Salvar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
