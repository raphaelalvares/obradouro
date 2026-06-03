import { ChevronLeft, FileUp, Package, ScrollText } from "lucide-react"
import { useState } from "react"
import { Link, useParams } from "react-router-dom"

import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { useObra } from "@/features/obras/obrasApi"
import { ImportNfeDialog } from "@/features/estoque/ImportNfeDialog"
import { NotaDetalheDialog } from "@/features/estoque/NotaDetalheDialog"
import {
  notaStatus,
  useNotas,
  useSaldo,
  type NotaResumo,
  type NotaStatus,
} from "@/features/estoque/estoqueApi"

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })
const num = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 })
const dataFmt = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" })

const STATUS_META: Record<NotaStatus, { label: string; cls: string }> = {
  pendente: { label: "Pendente", cls: "border-muted-foreground/40 text-muted-foreground" },
  parcial: { label: "Parcial", cls: "border-blue-500/50 text-blue-500" },
  divergente: { label: "Divergente", cls: "border-amber-500/50 text-amber-600" },
  conferida: { label: "Conferida", cls: "border-primary/50 text-primary" },
}

type Aba = "notas" | "saldo"

export function EstoquePage() {
  const { obraId = "" } = useParams()
  const obra = useObra(obraId)
  const ehArquiteto = obra.data?.meu_papel === "arquiteto"
  const [aba, setAba] = useState<Aba>("notas")
  const [importOpen, setImportOpen] = useState(false)
  const [notaSel, setNotaSel] = useState<string | null>(null)

  return (
    <div className="animate-fade-up">
      <Link
        to={`/obras/${obraId}`}
        className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronLeft className="size-4" />
        {obra.data?.nome ?? "Obra"}
      </Link>

      <div className="mb-5 flex items-end justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Materiais</div>
          <h1 className="font-word text-4xl leading-none">ESTOQUE</h1>
        </div>
        {ehArquiteto && (
          <Button onClick={() => setImportOpen(true)}>
            <FileUp />
            Importar NF-e
          </Button>
        )}
      </div>

      <div className="mb-5 inline-flex rounded-xl border border-border p-1">
        <AbaBtn ativo={aba === "notas"} onClick={() => setAba("notas")} label="Notas" />
        <AbaBtn ativo={aba === "saldo"} onClick={() => setAba("saldo")} label="Saldo" />
      </div>

      {aba === "notas" ? (
        <NotasView obraId={obraId} ehArquiteto={ehArquiteto} onAbrir={setNotaSel} />
      ) : (
        <SaldoView obraId={obraId} />
      )}

      {ehArquiteto && <ImportNfeDialog obraId={obraId} open={importOpen} onOpenChange={setImportOpen} />}
      <NotaDetalheDialog
        obraId={obraId}
        notaId={notaSel}
        ehArquiteto={ehArquiteto}
        podeConferir={ehArquiteto || obra.data?.meu_papel === "prestador"}
        onOpenChange={(o) => !o && setNotaSel(null)}
      />
    </div>
  )
}

function AbaBtn({ ativo, onClick, label }: { ativo: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-lg px-4 py-1.5 text-sm font-medium transition-colors",
        ativo ? "bg-accent text-primary" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {label}
    </button>
  )
}

const FILTROS: (NotaStatus | "todas")[] = ["todas", "pendente", "parcial", "divergente", "conferida"]

function NotasView({
  obraId,
  ehArquiteto,
  onAbrir,
}: {
  obraId: string
  ehArquiteto: boolean
  onAbrir: (id: string) => void
}) {
  const notas = useNotas(obraId)
  const [filtro, setFiltro] = useState<NotaStatus | "todas">("todas")

  if (notas.isLoading) return <CenteredSpinner />
  if (notas.isError)
    return <ErrorState message="Não foi possível carregar as notas." onRetry={() => void notas.refetch()} />

  const lista = notas.data ?? []
  if (lista.length === 0)
    return (
      <EmptyState
        icon={ScrollText}
        title="Nenhuma nota ainda"
        description={
          ehArquiteto
            ? "Importe o XML da NF-e para registrar a entrada de materiais."
            : "O arquiteto ainda não importou notas fiscais."
        }
      />
    )

  const filtrada = filtro === "todas" ? lista : lista.filter((n) => notaStatus(n) === filtro)

  return (
    <>
      <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
        {FILTROS.map((f) => {
          const n = f === "todas" ? lista.length : lista.filter((x) => notaStatus(x) === f).length
          const label = f === "todas" ? "Todas" : STATUS_META[f].label
          return (
            <button
              key={f}
              type="button"
              onClick={() => setFiltro(f)}
              className={cn(
                "shrink-0 rounded-full border px-3 py-1 text-xs transition-colors",
                filtro === f
                  ? "border-primary/50 bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {label} {n > 0 && <span className="opacity-60">{n}</span>}
            </button>
          )
        })}
      </div>

      {filtrada.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">Nenhuma nota nesse status.</p>
      ) : (
        <ul className="space-y-3">
          {filtrada.map((n) => (
            <li key={n.id}>
              <NotaCard nota={n} onClick={() => onAbrir(n.id)} />
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

function NotaCard({ nota, onClick }: { nota: NotaResumo; onClick: () => void }) {
  const st = STATUS_META[notaStatus(nota)]
  return (
    <button type="button" onClick={onClick} className="block w-full text-left">
      <Card className="p-4 transition-colors hover:border-primary/40">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-display text-sm text-muted-foreground">#{nota.seq_humano ?? "—"}</span>
              {nota.numero && <span className="text-sm text-muted-foreground">NF {nota.numero}</span>}
            </div>
            <h2 className="mt-0.5 truncate text-base font-medium">
              {nota.emitente_nome || "Emitente não informado"}
            </h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {nota.data_chegada
                ? `chegou ${dataFmt.format(new Date(nota.data_chegada))}`
                : nota.data_emissao
                  ? `emitida ${dataFmt.format(new Date(nota.data_emissao))}`
                  : "sem data"}
            </p>
          </div>
          <div className="shrink-0 text-right">
            <div className="font-medium">{brl.format(nota.valor_total)}</div>
            <div className="mt-1 flex flex-wrap justify-end gap-1">
              <span
                className={cn(
                  "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide",
                  st.cls,
                )}
              >
                {st.label}
              </span>
              <span className="rounded-full border border-border px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                {nota.itens_conferidos}/{nota.total_itens}
              </span>
            </div>
          </div>
        </div>
      </Card>
    </button>
  )
}

function SaldoView({ obraId }: { obraId: string }) {
  const saldo = useSaldo(obraId)

  if (saldo.isLoading) return <CenteredSpinner />
  if (saldo.isError)
    return <ErrorState message="Não foi possível carregar o saldo." onRetry={() => void saldo.refetch()} />
  if (saldo.data && saldo.data.length === 0)
    return (
      <EmptyState
        icon={Package}
        title="Sem materiais"
        description="Importe notas fiscais para ver o saldo de materiais da obra."
      />
    )

  const total = (saldo.data ?? []).reduce((s, i) => s + (i.valor_total ?? 0), 0)

  return (
    <div>
      <ul className="divide-y divide-border overflow-hidden rounded-2xl border border-border">
        {saldo.data?.map((i, idx) => (
          <li key={`${i.nome}-${i.unidade ?? ""}-${idx}`} className="flex items-center justify-between gap-3 bg-card p-4">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{i.nome}</div>
              <div className="text-xs text-muted-foreground">
                {num.format(i.quantidade_total)} {i.unidade ?? ""}
              </div>
            </div>
            <div className="shrink-0 text-sm">{brl.format(i.valor_total)}</div>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex items-center justify-between px-1 text-sm">
        <span className="text-muted-foreground">Total em materiais</span>
        <span className="font-medium">{brl.format(total)}</span>
      </div>
    </div>
  )
}
