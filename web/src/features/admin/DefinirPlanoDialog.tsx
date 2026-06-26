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
import { cn } from "@/lib/utils"

import { useDefinirPlano, type PlanoCatalogo, type TenantAdmin } from "./adminApi"

const ATALHOS_MESES = [1, 3, 6, 12]

/** Adiciona N meses a hoje e formata (preview da validade). */
function previewValidade(meses: number | null): string {
  if (meses === null) return "sem expiração"
  const d = new Date()
  d.setMonth(d.getMonth() + meses)
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" })
}

export function DefinirPlanoDialog({
  open,
  onOpenChange,
  tenant,
  planos,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  tenant: TenantAdmin | null
  planos: PlanoCatalogo[]
}) {
  const definir = useDefinirPlano()
  const [plano, setPlano] = useState("pro")
  const [meses, setMeses] = useState<number | null>(1)
  const [obs, setObs] = useState("")

  // ao (re)abrir, pré-preenche com o estado atual do tenant
  useEffect(() => {
    if (open && tenant) {
      const atual = tenant.plano_codigo !== "free" ? tenant.plano_codigo : "pro"
      setPlano(planos.some((p) => p.codigo === atual) ? atual : (planos[0]?.codigo ?? "pro"))
      setMeses(1)
      setObs(tenant.observacao ?? "")
      definir.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, tenant])

  if (!tenant) return null

  const podePagar = planos.filter((p) => p.codigo !== "free")

  function salvar() {
    if (!tenant) return
    definir.mutate(
      { tenantId: tenant.tenant_id, body: { plano, meses, observacao: obs.trim() || null } },
      { onSuccess: () => onOpenChange(false) },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Conceder cortesia / trial</DialogTitle>
          <DialogDescription>
            {tenant.nome_escritorio || tenant.nome || tenant.email} — exceção; o normal é assinar no
            Stripe.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-5">
          {/* plano */}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="admin-plano">Plano</Label>
            <select
              id="admin-plano"
              value={plano}
              onChange={(e) => setPlano(e.target.value)}
              className={cn(
                "flex h-11 w-full min-w-0 rounded-xl border border-input bg-card px-4 py-2 text-base sm:text-sm",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              )}
            >
              {podePagar.map((p) => (
                <option key={p.codigo} value={p.codigo}>
                  {p.nome}
                  {p.preco_mensal ? ` — R$ ${p.preco_mensal.toFixed(2)}/mês` : ""}
                </option>
              ))}
            </select>
          </div>

          {/* duração em meses */}
          <div className="flex flex-col gap-1.5">
            <Label>Duração</Label>
            <div className="flex flex-wrap gap-2">
              {ATALHOS_MESES.map((m) => (
                <Button
                  key={m}
                  type="button"
                  size="sm"
                  variant={meses === m ? "default" : "outline"}
                  onClick={() => setMeses(m)}
                >
                  {m} {m === 1 ? "mês" : "meses"}
                </Button>
              ))}
              <Button
                type="button"
                size="sm"
                variant={meses === null ? "default" : "outline"}
                onClick={() => setMeses(null)}
              >
                Sem expiração
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Expira em: <span className="font-medium text-foreground">{previewValidade(meses)}</span>
            </p>
          </div>

          {/* observação */}
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="admin-obs">Observação (opcional)</Label>
            <Input
              id="admin-obs"
              value={obs}
              onChange={(e) => setObs(e.target.value)}
              placeholder="ex.: cortesia, parceria, pagamento via Pix…"
            />
          </div>

          {definir.isError && (
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
            <Button
              type="button"
              className="flex-1"
              disabled={definir.isPending}
              onClick={salvar}
            >
              {definir.isPending && <Loader2 className="animate-spin" />}
              Conceder
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
