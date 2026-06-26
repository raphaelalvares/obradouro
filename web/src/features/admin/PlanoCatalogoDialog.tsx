import { Loader2 } from "lucide-react"
import { useEffect, useState } from "react"

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

import { useUpsertPlano, type PlanoCatalogo } from "./adminApi"

// Eixos conhecidos (preserva quaisquer outros já existentes no jsonb ao salvar).
const LIMITES = [
  { chave: "obras_ativas", rotulo: "Obras ativas" },
  { chave: "revisoes_projeto", rotulo: "Revisões/projeto" },
  { chave: "armazenamento_mb", rotulo: "Armazenamento (MB)" },
]
const FLAGS = [
  { chave: "export_pdf", rotulo: "Exportar PDF" },
  { chave: "logo", rotulo: "Logo/branding" },
  { chave: "chat", rotulo: "Chat" },
  { chave: "historico", rotulo: "Histórico" },
]

function vazio(): PlanoCatalogo {
  return { codigo: "", nome: "", limites: {}, flags: {}, preco_mensal: null, ativo: true, ordem: 0 }
}

export function PlanoCatalogoDialog({
  open,
  onOpenChange,
  plano,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  plano: PlanoCatalogo | null // null = criar novo
}) {
  const upsert = useUpsertPlano()
  const [form, setForm] = useState<PlanoCatalogo>(vazio())
  const novo = plano === null

  useEffect(() => {
    if (open) {
      setForm(plano ? { ...plano, limites: { ...plano.limites }, flags: { ...plano.flags } } : vazio())
      upsert.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, plano])

  function setLimite(chave: string, v: string) {
    const n = v.trim() === "" ? 0 : Number(v)
    setForm((f) => ({ ...f, limites: { ...f.limites, [chave]: Number.isFinite(n) ? n : 0 } }))
  }
  function setFlag(chave: string, v: boolean) {
    setForm((f) => ({ ...f, flags: { ...f.flags, [chave]: v } }))
  }

  function salvar() {
    const codigo = form.codigo.trim()
    if (!codigo || !form.nome.trim()) return
    const { codigo: _c, ...body } = form
    upsert.mutate({ codigo, body }, { onSuccess: () => onOpenChange(false) })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{novo ? "Novo plano" : `Editar plano · ${plano?.nome}`}</DialogTitle>
          <DialogDescription>Limites usam -1 para ilimitado.</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-5">
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pl-codigo">Código</Label>
              <Input
                id="pl-codigo"
                value={form.codigo}
                disabled={!novo}
                onChange={(e) => setForm((f) => ({ ...f, codigo: e.target.value }))}
                placeholder="ex.: pro"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pl-nome">Nome</Label>
              <Input
                id="pl-nome"
                value={form.nome}
                onChange={(e) => setForm((f) => ({ ...f, nome: e.target.value }))}
                placeholder="ex.: Pro"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pl-preco">Preço mensal (R$)</Label>
              <Input
                id="pl-preco"
                inputMode="decimal"
                value={form.preco_mensal ?? ""}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    preco_mensal: e.target.value.trim() === "" ? null : Number(e.target.value),
                  }))
                }
                placeholder="0,00"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="pl-ordem">Ordem</Label>
              <Input
                id="pl-ordem"
                inputMode="numeric"
                value={form.ordem}
                onChange={(e) => setForm((f) => ({ ...f, ordem: Number(e.target.value) || 0 }))}
              />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label>Limites</Label>
            <div className="grid grid-cols-3 gap-3">
              {LIMITES.map((l) => (
                <div key={l.chave} className="flex flex-col gap-1">
                  <span className="text-xs text-muted-foreground">{l.rotulo}</span>
                  <Input
                    inputMode="numeric"
                    value={form.limites[l.chave] ?? 0}
                    onChange={(e) => setLimite(l.chave, e.target.value)}
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label>Recursos</Label>
            <div className="grid grid-cols-2 gap-2">
              {FLAGS.map((fl) => (
                <label key={fl.chave} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="size-4 accent-primary"
                    checked={Boolean(form.flags[fl.chave])}
                    onChange={(e) => setFlag(fl.chave, e.target.checked)}
                  />
                  {fl.rotulo}
                </label>
              ))}
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-primary"
              checked={form.ativo}
              onChange={(e) => setForm((f) => ({ ...f, ativo: e.target.checked }))}
            />
            Disponível para novos clientes
          </label>

          {upsert.isError && (
            <p className="text-sm text-destructive">Não foi possível salvar. Tente de novo.</p>
          )}

          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              className="flex-1"
              onClick={() => onOpenChange(false)}
            >
              Cancelar
            </Button>
            <Button type="button" className="flex-1" disabled={upsert.isPending} onClick={salvar}>
              {upsert.isPending && <Loader2 className="animate-spin" />}
              Salvar
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
