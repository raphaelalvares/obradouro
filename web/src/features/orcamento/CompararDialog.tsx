import { ArrowRight, Loader2 } from "lucide-react"
import { useEffect, useState } from "react"

import { ErrorState } from "@/components/feedback/states"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"
import { formatBRL } from "@/features/comercial/format"
import { useVersao, type OrcVersaoResumo } from "@/features/orcamento/orcamentosApi"

const selectCls = cn(
  "flex h-10 w-full min-w-0 rounded-xl border border-input bg-card px-3 py-1 text-sm",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
)

function Delta({ a, b }: { a: number; b: number }) {
  const d = b - a
  if (Math.abs(d) < 0.005) return <span className="text-muted-foreground">—</span>
  const pct = a !== 0 ? ` (${d > 0 ? "+" : ""}${((d / a) * 100).toFixed(1).replace(".", ",")}%)` : ""
  return (
    <span className={d > 0 ? "text-destructive" : "text-primary"}>
      {d > 0 ? "+" : "−"}
      {formatBRL(Math.abs(d))}
      <span className="text-[10px]">{pct}</span>
    </span>
  )
}

/** Comparação de duas versões do orçamento (R0 × R1): totais e custo direto por etapa, lado a
 * lado, com a variação. Leitura pura — nada é alterado. */
export function CompararDialog({
  open,
  onOpenChange,
  projetoId,
  versoes,
  versaoAtualId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projetoId: string
  versoes: OrcVersaoResumo[]
  versaoAtualId: string | null
}) {
  const [aId, setAId] = useState<string | null>(null)
  const [bId, setBId] = useState<string | null>(null)

  // padrão: B = versão aberta na tela; A = a imediatamente anterior
  useEffect(() => {
    if (!open || versoes.length < 2) return
    const bIdx = Math.max(
      versoes.findIndex((v) => v.id === versaoAtualId),
      1, // se a aberta for a R0 (ou não achada), compara R0 × R1
    )
    setBId(versoes[bIdx].id)
    setAId(versoes[bIdx - 1].id)
  }, [open, versoes, versaoAtualId])

  const a = useVersao(projetoId, open ? aId : null)
  const b = useVersao(projetoId, open ? bId : null)
  const carregando = a.isLoading || b.isLoading

  // etapas alinhadas por NOME: ordem da versão B; as que só existem em A vão ao final
  const linhas: { etapa: string; a: number | null; b: number | null }[] = []
  if (a.data && b.data) {
    const deA = new Map(a.data.etapas.map((g) => [g.etapa, g.custo_direto]))
    for (const g of b.data.etapas) {
      linhas.push({ etapa: g.etapa, a: deA.get(g.etapa) ?? null, b: g.custo_direto })
      deA.delete(g.etapa)
    }
    for (const [etapa, val] of deA) linhas.push({ etapa, a: val, b: null })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Comparar versões</DialogTitle>
          <DialogDescription>
            Custo direto por etapa e totais, lado a lado. A variação é de A para B.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-2">
          <select
            aria-label="Versão A"
            className={selectCls}
            value={aId ?? ""}
            onChange={(e) => setAId(e.target.value)}
          >
            {versoes.map((v) => (
              <option key={v.id} value={v.id}>
                R{v.numero} · {formatBRL(v.preco_final)}
              </option>
            ))}
          </select>
          <ArrowRight className="size-4 shrink-0 text-muted-foreground" />
          <select
            aria-label="Versão B"
            className={selectCls}
            value={bId ?? ""}
            onChange={(e) => setBId(e.target.value)}
          >
            {versoes.map((v) => (
              <option key={v.id} value={v.id}>
                R{v.numero} · {formatBRL(v.preco_final)}
              </option>
            ))}
          </select>
        </div>

        {carregando && (
          <div className="flex justify-center py-8">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          </div>
        )}

        {!carregando && (a.isError || b.isError) && (
          <ErrorState
            message="Não foi possível carregar as versões."
            onRetry={() => {
              void a.refetch()
              void b.refetch()
            }}
          />
        )}

        {a.data && b.data && (
          <div className="max-h-[60vh] overflow-y-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="py-2 pr-2 font-medium">&nbsp;</th>
                  <th className="py-2 pr-2 text-right font-medium">R{a.data.numero}</th>
                  <th className="py-2 pr-2 text-right font-medium">R{b.data.numero}</th>
                  <th className="py-2 text-right font-medium">Variação</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {linhas.map((l) => (
                  <tr key={l.etapa} className="border-b border-border/60">
                    <td className="max-w-[10rem] break-words py-2 pr-2 text-xs">{l.etapa}</td>
                    <td className="py-2 pr-2 text-right text-muted-foreground">
                      {l.a != null ? formatBRL(l.a) : "—"}
                    </td>
                    <td className="py-2 pr-2 text-right">{l.b != null ? formatBRL(l.b) : "—"}</td>
                    <td className="py-2 text-right text-xs">
                      <Delta a={l.a ?? 0} b={l.b ?? 0} />
                    </td>
                  </tr>
                ))}
                <tr className="border-b border-border/60">
                  <td className="py-2 pr-2 text-xs text-muted-foreground">Custo direto</td>
                  <td className="py-2 pr-2 text-right text-muted-foreground">
                    {formatBRL(a.data.totais.custo_direto)}
                  </td>
                  <td className="py-2 pr-2 text-right">{formatBRL(b.data.totais.custo_direto)}</td>
                  <td className="py-2 text-right text-xs">
                    <Delta a={a.data.totais.custo_direto} b={b.data.totais.custo_direto} />
                  </td>
                </tr>
                <tr className="border-b border-border/60 text-xs text-muted-foreground">
                  <td className="py-2 pr-2">BDI · Imposto</td>
                  <td className="py-2 pr-2 text-right">
                    {formatBRL(a.data.totais.bdi_valor + a.data.totais.imposto_valor)}
                  </td>
                  <td className="py-2 pr-2 text-right">
                    {formatBRL(b.data.totais.bdi_valor + b.data.totais.imposto_valor)}
                  </td>
                  <td className="py-2 text-right">
                    <Delta
                      a={a.data.totais.bdi_valor + a.data.totais.imposto_valor}
                      b={b.data.totais.bdi_valor + b.data.totais.imposto_valor}
                    />
                  </td>
                </tr>
                <tr className="font-medium">
                  <td className="py-2.5 pr-2 text-xs uppercase tracking-wide">Preço final</td>
                  <td className="py-2.5 pr-2 text-right text-muted-foreground">
                    {formatBRL(a.data.totais.preco_final)}
                  </td>
                  <td className="py-2.5 pr-2 text-right font-display">
                    {formatBRL(b.data.totais.preco_final)}
                  </td>
                  <td className="py-2.5 text-right text-xs">
                    <Delta a={a.data.totais.preco_final} b={b.data.totais.preco_final} />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
