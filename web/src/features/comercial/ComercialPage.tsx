import { CalendarClock, Plus, Target } from "lucide-react"
import { useMemo, useState } from "react"

import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  ETAPAS,
  etapaMeta,
  useOportunidades,
  type EtapaOportunidade,
  type Oportunidade,
} from "@/features/comercial/comercialApi"
import { followupStatus, formatBRL, formatData, hojeISO } from "@/features/comercial/format"
import { OportunidadeDetalheDialog } from "@/features/comercial/OportunidadeDetalheDialog"
import { OportunidadeFormDialog } from "@/features/comercial/OportunidadeFormDialog"

type EstadoForm = null | "novo" | Oportunidade
const vazioPorEtapa = (): Record<EtapaOportunidade, Oportunidade[]> => ({
  lead: [],
  contato: [],
  visita: [],
  proposta: [],
  ganho: [],
  perdido: [],
})

export function ComercialPage() {
  const [form, setForm] = useState<EstadoForm>(null)
  const [detalhe, setDetalhe] = useState<Oportunidade | null>(null)
  const [etapaSel, setEtapaSel] = useState<EtapaOportunidade>("lead")
  const ops = useOportunidades()
  const hoje = hojeISO()

  const grupos = useMemo(() => {
    const g = vazioPorEtapa()
    for (const o of ops.data ?? []) g[o.etapa].push(o)
    return g
  }, [ops.data])

  const abertos = (ops.data ?? []).filter((o) => o.etapa !== "ganho" && o.etapa !== "perdido")
  const valorAberto = abertos.reduce((s, o) => s + (o.valor_estimado ?? 0), 0)

  // detalhe sempre com o dado MAIS NOVO do cache (reflete o move-de-etapa otimista sem fechar o sheet).
  const detalheLive = detalhe ? (ops.data?.find((o) => o.id === detalhe.id) ?? detalhe) : null

  return (
    <div className="animate-fade-up">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Funil comercial</div>
          <h1 className="font-word text-4xl leading-none">COMERCIAL</h1>
        </div>
        <Button onClick={() => setForm("novo")}>
          <Plus />
          Nova
        </Button>
      </div>

      {ops.isSuccess && ops.data.length > 0 && (
        <p className="mb-4 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{abertos.length}</span> em aberto ·{" "}
          <span className="font-medium text-foreground">{formatBRL(valorAberto)}</span> em negociação
        </p>
      )}

      {ops.isLoading && <CenteredSpinner />}

      {ops.isError && (
        <ErrorState
          message="Não foi possível carregar o funil."
          onRetry={() => void ops.refetch()}
        />
      )}

      {ops.isSuccess && ops.data.length === 0 && (
        <EmptyState
          icon={Target}
          title="Nenhuma oportunidade ainda"
          description="Cadastre o primeiro lead para começar a acompanhar o funil comercial."
          action={
            <Button onClick={() => setForm("novo")}>
              <Plus />
              Cadastrar oportunidade
            </Button>
          }
        />
      )}

      {ops.isSuccess && ops.data.length > 0 && (
        <>
          {/* MOBILE: seletor de etapa + lista vertical larga (sem ...) */}
          <div className="sm:hidden">
            <div className="-mx-5 mb-3 flex gap-1.5 overflow-x-auto px-5 pb-1">
              {ETAPAS.map((et) => {
                const ativo = etapaSel === et.key
                return (
                  <button
                    key={et.key}
                    type="button"
                    onClick={() => setEtapaSel(et.key)}
                    className={cn(
                      "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                      ativo
                        ? "border-transparent"
                        : "border-border text-muted-foreground hover:text-foreground",
                    )}
                    style={ativo ? { background: et.cor, color: "#1a1505" } : undefined}
                  >
                    {et.label}
                    <span
                      className={cn(
                        "rounded-full px-1.5 text-[10px]",
                        ativo ? "bg-black/15" : "bg-muted text-muted-foreground",
                      )}
                    >
                      {grupos[et.key].length}
                    </span>
                  </button>
                )
              })}
            </div>
            <div className="space-y-2">
              {grupos[etapaSel].map((op) => (
                <CardOportunidade key={op.id} op={op} hoje={hoje} onClick={() => setDetalhe(op)} />
              ))}
              {grupos[etapaSel].length === 0 && (
                <p className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                  Nenhuma oportunidade em {etapaMeta(etapaSel).label}.
                </p>
              )}
            </div>
          </div>

          {/* DESKTOP: quadro com colunas (rola na horizontal) */}
          <div className="hidden sm:block">
            <div className="flex gap-3 overflow-x-auto pb-2">
              {ETAPAS.map((et) => (
                <div key={et.key} className="flex w-64 shrink-0 flex-col gap-2">
                  <div className="flex items-center gap-2 px-1">
                    <span className="size-2 rounded-full" style={{ background: et.cor }} />
                    <span className="text-xs font-semibold uppercase tracking-wide">{et.label}</span>
                    <span className="text-xs text-muted-foreground">{grupos[et.key].length}</span>
                  </div>
                  {grupos[et.key].map((op) => (
                    <CardOportunidade
                      key={op.id}
                      op={op}
                      hoje={hoje}
                      onClick={() => setDetalhe(op)}
                    />
                  ))}
                  {grupos[et.key].length === 0 && (
                    <p className="px-1 text-xs text-muted-foreground/70">—</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      <OportunidadeFormDialog
        open={form !== null}
        onOpenChange={(o) => {
          if (!o) setForm(null)
        }}
        oportunidade={typeof form === "object" ? form : null}
      />
      <OportunidadeDetalheDialog
        open={detalhe !== null}
        onOpenChange={(o) => {
          if (!o) setDetalhe(null)
        }}
        oportunidade={detalheLive}
        onEditar={(op) => {
          setDetalhe(null)
          setForm(op)
        }}
      />
    </div>
  )
}

function CardOportunidade({
  op,
  hoje,
  onClick,
}: {
  op: Oportunidade
  hoje: string
  onClick: () => void
}) {
  const fu = followupStatus(op.proximo_followup, hoje)
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full rounded-xl border border-border bg-card p-3 text-left transition-colors hover:border-primary/40"
    >
      <div className="flex items-start gap-2">
        <span
          className="mt-1 size-2 shrink-0 rounded-full"
          style={{ background: etapaMeta(op.etapa).cor }}
          aria-hidden
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-1.5">
            <span className="shrink-0 font-display text-[11px] text-muted-foreground">
              #{op.seq_humano ?? "—"}
            </span>
            <p className="min-w-0 break-words text-sm font-medium">{op.nome}</p>
          </div>
          {op.contato_nome && (
            <p className="mt-0.5 break-words text-xs text-muted-foreground">{op.contato_nome}</p>
          )}
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            {op.valor_estimado != null && (
              <span className="font-medium text-foreground">{formatBRL(op.valor_estimado)}</span>
            )}
            {op.proximo_followup && (
              <span
                className={cn(
                  "inline-flex items-center gap-1 text-muted-foreground",
                  fu === "atrasado" && "text-destructive",
                  fu === "hoje" && "text-primary",
                )}
              >
                <CalendarClock className="size-3" />
                {formatData(op.proximo_followup)}
              </span>
            )}
            {op.origem && <span className="break-words text-muted-foreground">{op.origem}</span>}
          </div>
        </div>
      </div>
    </button>
  )
}
