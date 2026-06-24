import { CalendarClock, FolderKanban, MessageSquare, Plus, Target } from "lucide-react"
import { useMemo, useState, type CSSProperties, type ReactNode } from "react"

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
import { ComentariosDialog } from "@/features/comercial/ComentariosDialog"
import { LembretesCard } from "@/features/comercial/LembretesCard"
import { OportunidadeDetalheDialog } from "@/features/comercial/OportunidadeDetalheDialog"
import { OportunidadeFormDialog } from "@/features/comercial/OportunidadeFormDialog"
import { VincularProjetoDialog } from "@/features/comercial/VincularProjetoDialog"

type EstadoForm = null | "novo" | Oportunidade
const GANHO_COR = "#5FB87A"
const PERDIDO_COR = "#E5654B"

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
  const [comentariosDe, setComentariosDe] = useState<Oportunidade | null>(null)
  const [vinculandoDe, setVinculandoDe] = useState<Oportunidade | null>(null)
  const [etapaSel, setEtapaSel] = useState<EtapaOportunidade>("lead")
  const ops = useOportunidades()
  const hoje = hojeISO()

  // Agregados do painel (grupos + KPIs + subtotais por coluna) num único memo.
  const stats = useMemo(() => {
    const grupos = vazioPorEtapa()
    const data = ops.data ?? []
    for (const o of data) grupos[o.etapa].push(o)
    const soma = (arr: Oportunidade[]) => arr.reduce((s, o) => s + (o.valor_estimado ?? 0), 0)
    const abertos = data.filter((o) => o.etapa !== "ganho" && o.etapa !== "perdido")
    const g = grupos.ganho.length
    const p = grupos.perdido.length
    const subtotal = {} as Record<EtapaOportunidade, number>
    const temAtrasado = {} as Record<EtapaOportunidade, boolean>
    for (const et of ETAPAS) {
      subtotal[et.key] = soma(grupos[et.key])
      temAtrasado[et.key] = grupos[et.key].some(
        (o) => followupStatus(o.proximo_followup, hoje) === "atrasado",
      )
    }
    return {
      grupos,
      abertosLen: abertos.length,
      valorAberto: soma(abertos),
      valorGanho: subtotal.ganho,
      ganhosLen: g,
      valorPerd: subtotal.perdido,
      perdLen: p,
      conv: g + p > 0 ? Math.round((g / (g + p)) * 100) : null,
      atrasados: data.filter((o) => followupStatus(o.proximo_followup, hoje) === "atrasado").length,
      hojeFu: data.filter((o) => followupStatus(o.proximo_followup, hoje) === "hoje").length,
      subtotal,
      temAtrasado,
    }
  }, [ops.data, hoje])

  // dialogs sempre com o dado MAIS NOVO do cache (refletem mutações otimistas sem fechar a folha).
  const vivo = (op: Oportunidade | null) =>
    op ? (ops.data?.find((o) => o.id === op.id) ?? op) : null

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

      {/* resumo (só mobile — no desktop os KPIs cobrem isto) */}
      {ops.isSuccess && ops.data.length > 0 && (
        <p className="mb-4 text-sm text-muted-foreground sm:hidden">
          <span className="font-medium text-foreground">{stats.abertosLen}</span> em aberto ·{" "}
          <span className="font-medium text-foreground">{formatBRL(stats.valorAberto)}</span> em
          negociação
        </p>
      )}

      <LembretesCard
        onAbrir={(opId) => {
          const o = ops.data?.find((x) => x.id === opId)
          if (o) setDetalhe(o)
        }}
      />

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
                      {stats.grupos[et.key].length}
                    </span>
                  </button>
                )
              })}
            </div>
            <div className="space-y-2">
              {stats.grupos[etapaSel].map((op) => (
                <CardOportunidade
                  key={op.id}
                  op={op}
                  hoje={hoje}
                  onClick={() => setDetalhe(op)}
                  onComentarios={() => setComentariosDe(op)}
                />
              ))}
              {stats.grupos[etapaSel].length === 0 && (
                <p className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                  Nenhuma oportunidade em {etapaMeta(etapaSel).label}.
                </p>
              )}
            </div>
          </div>

          {/* DESKTOP: painel (KPIs + quadro de 6 colunas preenchendo a largura) */}
          <div className="hidden sm:block">
            <div className="mb-6 grid grid-cols-3 gap-3 xl:grid-cols-6">
              <Kpi label="Em aberto" valor={String(stats.abertosLen)} sub="oportunidades" />
              <Kpi
                label="Em negociação"
                valor={formatBRL(stats.valorAberto)}
                sub={`${stats.abertosLen} abertas`}
                valorClass="text-primary"
              />
              <Kpi
                label="Ganhos"
                valor={formatBRL(stats.valorGanho)}
                sub={`${stats.ganhosLen} ganhas`}
                style={{ color: GANHO_COR }}
              />
              <Kpi
                label="Conversão"
                valor={stats.conv == null ? "—" : `${stats.conv}%`}
                sub={`${stats.ganhosLen} de ${stats.ganhosLen + stats.perdLen} fechadas`}
                valorClass={stats.conv == null ? "text-muted-foreground" : undefined}
              >
                <div className="mt-2 h-1.5 w-full rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary"
                    style={{ width: `${stats.conv ?? 0}%` }}
                  />
                </div>
              </Kpi>
              <Kpi
                label="Follow-up"
                valor={String(stats.atrasados)}
                sub={`${stats.hojeFu} hoje`}
                valorClass={stats.atrasados > 0 ? "text-destructive" : "text-muted-foreground"}
              />
              <Kpi
                label="Perdidos"
                valor={formatBRL(stats.valorPerd)}
                sub={`${stats.perdLen} perdidas`}
                style={{ color: PERDIDO_COR }}
                className="hidden xl:flex"
              />
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-3 lg:grid-cols-6">
              {ETAPAS.map((et) => {
                const subCor =
                  et.key === "ganho" ? GANHO_COR : et.key === "perdido" ? PERDIDO_COR : undefined
                return (
                  <div
                    key={et.key}
                    className={cn(
                      "flex min-w-0 flex-col rounded-2xl border border-border bg-card/40",
                      stats.temAtrasado[et.key] && "ring-1 ring-destructive/30",
                    )}
                  >
                    <div
                      className="rounded-t-2xl border-b-2 px-3 py-2"
                      style={{ borderBottomColor: et.cor }}
                    >
                      <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide">
                        <span className="size-2 rounded-full" style={{ background: et.cor }} />
                        {et.label}
                        <span className="ml-auto rounded-full bg-muted px-1.5 py-0.5 text-[10px] tabular-nums text-muted-foreground">
                          {stats.grupos[et.key].length}
                        </span>
                      </span>
                      <span className="mt-0.5 flex items-center gap-2">
                        <span className="font-display text-sm tabular-nums" style={subCor ? { color: subCor } : undefined}>
                          {formatBRL(stats.subtotal[et.key])}
                        </span>
                        {stats.temAtrasado[et.key] && (
                          <span className="text-[10px] font-medium text-destructive">⚠ atrasado</span>
                        )}
                      </span>
                    </div>
                    <div className="flex flex-1 flex-col gap-2 overflow-y-auto p-2 max-h-[calc(100dvh-20rem)]">
                      {stats.grupos[et.key].map((op) => (
                        <CardOportunidade
                          key={op.id}
                          op={op}
                          hoje={hoje}
                          onClick={() => setDetalhe(op)}
                          onComentarios={() => setComentariosDe(op)}
                        />
                      ))}
                      {stats.grupos[et.key].length === 0 && (
                        <p className="rounded-xl border border-dashed border-border px-2 py-6 text-center text-xs text-muted-foreground/70">
                          —
                        </p>
                      )}
                    </div>
                  </div>
                )
              })}
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
        oportunidade={vivo(detalhe)}
        onEditar={(op) => {
          setDetalhe(null)
          setForm(op)
        }}
        onComentarios={(op) => {
          setDetalhe(null)
          setComentariosDe(op)
        }}
        onVincularProjeto={(op) => {
          setDetalhe(null)
          setVinculandoDe(op)
        }}
      />
      <ComentariosDialog
        open={comentariosDe !== null}
        onOpenChange={(o) => {
          if (!o) setComentariosDe(null)
        }}
        oportunidade={vivo(comentariosDe)}
      />
      <VincularProjetoDialog
        open={vinculandoDe !== null}
        onOpenChange={(o) => {
          if (!o) setVinculandoDe(null)
        }}
        oportunidade={vivo(vinculandoDe)}
      />
    </div>
  )
}

function Kpi({
  label,
  valor,
  sub,
  valorClass,
  style,
  className,
  children,
}: {
  label: string
  valor: string
  sub?: string
  valorClass?: string
  style?: CSSProperties
  className?: string
  children?: ReactNode
}) {
  return (
    <div className={cn("flex flex-col rounded-2xl border border-border bg-card p-3", className)}>
      <span className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </span>
      <span className={cn("mt-1 font-display text-xl leading-none tabular-nums", valorClass)} style={style}>
        {valor}
      </span>
      {sub && <span className="mt-0.5 text-xs text-muted-foreground">{sub}</span>}
      {children}
    </div>
  )
}

function CardOportunidade({
  op,
  hoje,
  onClick,
  onComentarios,
}: {
  op: Oportunidade
  hoje: string
  onClick: () => void
  onComentarios: () => void
}) {
  const fu = followupStatus(op.proximo_followup, hoje)
  return (
    <div className="relative w-full rounded-xl border border-border bg-card transition-colors hover:border-primary/40">
      <button type="button" onClick={onClick} className="block w-full p-3 pr-9 text-left">
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
              {op.projeto_id && (
                <span
                  className="inline-flex items-center gap-1 text-muted-foreground"
                  title="Projeto vinculado"
                >
                  <FolderKanban className="size-3" />
                </span>
              )}
            </div>
          </div>
        </div>
      </button>

      {/* acesso rápido aos comentários (não abre o detalhe) */}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          onComentarios()
        }}
        aria-label="Comentários"
        title="Comentários"
        className="absolute right-1.5 top-1.5 inline-flex items-center gap-0.5 rounded-md px-1.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <MessageSquare className="size-3.5" />
        {op.comentarios_count > 0 && <span className="tabular-nums">{op.comentarios_count}</span>}
      </button>
    </div>
  )
}
