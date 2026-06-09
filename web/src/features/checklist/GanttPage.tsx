import { ChartGantt, ChevronLeft, Printer } from "lucide-react"
import { Link, useParams } from "react-router-dom"

import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { useChecklist } from "@/features/checklist/checklistApi"
import { formatBR, formatIntervalo } from "@/features/checklist/cronograma"
import {
  barraPos,
  hojeISO,
  montarGantt,
  type GanttModelo,
  type GanttRow,
  type GanttStatus,
} from "@/features/checklist/gantt"
import { useObra } from "@/features/obras/obrasApi"

// Cores de SITUAÇÃO (iguais na tela e no papel — leem bem nos dois). Os tons de superfície/texto/
// linha vêm de CSS vars (.gantt-print) que trocam escuro→claro no @media print (ver index.css).
const DONE = "#5FB87A"
const LATE = "#E5654B"
const GOLD = "#D8A53A"
const PROGRESS = "rgba(0,0,0,0.28)" // parte preenchida da barra = concluído
const NOME_COL_PX = 200
const PX_POR_DIA = 16

function corStatus(s: GanttStatus): string {
  return s === "concluido" ? DONE : s === "atrasado" ? LATE : GOLD
}

const pct = (n: number) => `${Math.round(n * 100)}%`

export function GanttPage() {
  const { obraId = "" } = useParams()
  const obra = useObra(obraId)
  const tree = useChecklist(obraId)

  const etapas = tree.data?.etapas ?? []
  const modelo = montarGantt(etapas, hojeISO())

  return (
    <div className="animate-fade-up">
      {/* barra de ações — não vai para a impressão */}
      <div className="no-print mb-4 flex items-center justify-between gap-3">
        <Link
          to={`/obras/${obraId}/cronograma`}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronLeft className="size-4" />
          Cronograma
        </Link>
        {modelo && (
          <Button onClick={() => window.print()}>
            <Printer />
            Imprimir / Salvar PDF
          </Button>
        )}
      </div>

      {tree.isLoading && <CenteredSpinner />}
      {tree.isError && (
        <ErrorState message="Não foi possível carregar o cronograma." onRetry={() => void tree.refetch()} />
      )}

      {tree.isSuccess && !modelo && (
        <EmptyState
          icon={ChartGantt}
          title="Sem datas para exibir"
          description="Preencha as datas das tarefas (ou use o Cronograma macro) para gerar o gráfico de Gantt."
          action={
            <Button asChild variant="outline">
              <Link to={`/obras/${obraId}/cronograma`}>Voltar ao cronograma</Link>
            </Button>
          }
        />
      )}

      {modelo && (
        <div
          className="gantt-print overflow-hidden rounded-2xl text-[13px]"
          style={{ background: "var(--g-bg)", color: "var(--g-ink)", border: "1px solid var(--g-line)" }}
        >
          <DocHeader
            titulo={obra.data?.nome ?? "Obra"}
            seq={obra.data?.seq_humano ?? null}
            modelo={modelo}
          />
          <Grafico modelo={modelo} />
          <div
            className="flex items-center justify-between px-5 py-3 text-[11px]"
            style={{ borderTop: "1px solid var(--g-line)", color: "var(--g-muted)" }}
          >
            <span>Gerado em {formatBR(hojeISO())} · obradouro.com.br</span>
            <span>{modelo.rows.filter((r) => r.kind === "tarefa").length} tarefa(s) agendada(s)</span>
          </div>
        </div>
      )}
    </div>
  )
}

function DocHeader({
  titulo,
  seq,
  modelo,
}: {
  titulo: string
  seq: number | null
  modelo: GanttModelo
}) {
  return (
    <div className="px-5 pt-5" style={{ background: "var(--g-surface)", borderBottom: "1px solid var(--g-line)" }}>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.3em]" style={{ color: GOLD }}>
            Obra #{seq ?? "—"} · Cronograma
          </div>
          <h1 className="font-display text-2xl font-light leading-tight" style={{ color: "var(--g-ink)" }}>
            {titulo}
          </h1>
        </div>
        <div className="text-right text-[11px]" style={{ color: "var(--g-muted)" }}>
          <div>
            {formatBR(modelo.min)} — {formatBR(modelo.max)}
          </div>
          <div>{modelo.totalDias} dias</div>
        </div>
      </div>

      {modelo.progressoGeral != null && (
        <div className="mt-3 flex items-center gap-3">
          <div
            className="h-1.5 flex-1 overflow-hidden rounded-full"
            style={{ background: "var(--g-line)" }}
          >
            <div
              className="h-full rounded-full"
              style={{ width: pct(modelo.progressoGeral), background: DONE }}
            />
          </div>
          <span className="shrink-0 font-display text-sm" style={{ color: DONE }}>
            {pct(modelo.progressoGeral)} concluído
          </span>
        </div>
      )}

      <Legenda />
    </div>
  )
}

function Legenda() {
  const item = (cor: string, txt: string) => (
    <span className="inline-flex items-center gap-1.5">
      <span className="h-2.5 w-5 rounded-md" style={{ background: cor }} />
      {txt}
    </span>
  )
  return (
    <div
      className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3 text-[11px]"
      style={{ color: "var(--g-muted)" }}
    >
      {item(GOLD, "Previsto")}
      {item(DONE, "Concluído")}
      {item(LATE, "Atrasado")}
      <span className="inline-flex items-center gap-1.5">
        <span className="inline-block h-3 w-0 border-l-2 border-dashed" style={{ borderColor: "var(--g-today)" }} />
        Hoje
      </span>
      <span className="opacity-70">parte preenchida = concluído</span>
    </div>
  )
}

function Grafico({ modelo }: { modelo: GanttModelo }) {
  // largura mínima no celular → rola na horizontal; na impressão o CSS força min-width:0 (cabe na
  // página). Tabela p/ o <thead> (faixa de meses) REPETIR em cada folha impressa.
  const minWidth = modelo.totalDias * PX_POR_DIA + NOME_COL_PX + 30
  return (
    <div className="gantt-scroll overflow-x-auto">
      <table
        className="gantt-inner w-full"
        style={{ minWidth, tableLayout: "fixed", borderCollapse: "separate", borderSpacing: 0 }}
      >
        <colgroup>
          <col style={{ width: NOME_COL_PX }} />
          <col />
        </colgroup>
        <thead>
          <tr>
            <th className="sticky left-0 z-20 p-0" style={{ background: "var(--g-surface)" }} />
            <th className="p-0" style={{ borderBottom: "1px solid var(--g-line)", background: "var(--g-surface)" }}>
              <div className="relative h-7">
                {modelo.meses.map((mes, i) => (
                  <div
                    key={i}
                    className="absolute top-0 truncate px-1.5 text-left text-[10px] font-normal uppercase tracking-wide"
                    style={{
                      left: `${mes.leftPct}%`,
                      width: `${mes.widthPct}%`,
                      color: "var(--g-muted)",
                      borderLeft: i === 0 ? undefined : "1px solid var(--g-line-strong)",
                      lineHeight: "1.75rem",
                    }}
                  >
                    {mes.label}
                  </div>
                ))}
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          {modelo.rows.map((row) => (
            <Linha key={`${row.kind}-${row.id}`} row={row} modelo={modelo} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Linha({ row, modelo }: { row: GanttRow; modelo: GanttModelo }) {
  const etapa = row.kind === "etapa"
  const pos = barraPos(modelo, row.inicio, row.fim)
  const rowBg = etapa ? "var(--g-etapa-row)" : "var(--g-bg)"
  const cor = corStatus(row.status)
  const intervalo = formatIntervalo(row.inicio, row.fim)
  const temProg = row.progresso != null && row.progresso > 0 && row.progresso < 1
  const titulo = intervalo + (row.progresso != null ? ` · ${pct(row.progresso)} concluído` : "")
  return (
    <tr className="gantt-row">
      <td
        className="sticky left-0 z-20 px-3 py-2 align-top"
        style={{ background: rowBg, borderBottom: "1px solid var(--g-line)" }}
      >
        <div className="flex items-baseline gap-1.5">
          <span
            className="mt-1 size-2 shrink-0 self-start rounded-full"
            style={{ background: cor }}
            aria-hidden
          />
          {row.seq != null && (
            <span className="shrink-0 font-display text-[11px]" style={{ color: "var(--g-muted)" }}>
              #{row.seq}
            </span>
          )}
          <span
            className={`break-words ${etapa ? "text-[13px] font-semibold" : "text-[12px]"}`}
            style={{ color: "var(--g-ink)" }}
          >
            {row.nome}
          </span>
          {etapa && row.progresso != null && (
            <span className="ml-auto shrink-0 pl-2 font-display text-[11px]" style={{ color: "var(--g-muted)" }}>
              {pct(row.progresso)}
            </span>
          )}
        </div>
      </td>

      <td className="p-0" style={{ background: rowBg, borderBottom: "1px solid var(--g-line)" }}>
        <div className="relative min-h-[2.25rem]">
          <Grade modelo={modelo} />
          {pos && (
            <div
              className={`absolute top-1/2 -translate-y-1/2 overflow-hidden ${etapa ? "h-2 rounded-full" : "h-3.5 rounded-md"}`}
              title={titulo}
              style={{
                left: `${pos.leftPct}%`,
                width: `${pos.widthPct}%`,
                minWidth: 3,
                background: cor,
                boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.08)",
              }}
            >
              {temProg && row.status !== "concluido" && (
                <div
                  className="h-full"
                  style={{ width: pct(row.progresso as number), background: PROGRESS }}
                />
              )}
            </div>
          )}
        </div>
      </td>
    </tr>
  )
}

function Grade({ modelo }: { modelo: GanttModelo }) {
  return (
    <div className="pointer-events-none absolute inset-0">
      {modelo.semanas.map((left, i) => (
        <div
          key={`w${i}`}
          className="absolute inset-y-0"
          style={{ left: `${left}%`, borderLeft: "1px solid var(--g-line)" }}
        />
      ))}
      {modelo.meses.map((mes, i) =>
        i === 0 ? null : (
          <div
            key={`m${i}`}
            className="absolute inset-y-0"
            style={{ left: `${mes.leftPct}%`, borderLeft: "1px solid var(--g-line-strong)" }}
          />
        ),
      )}
      {modelo.hojeLeftPct != null && (
        <div
          className="absolute inset-y-0 border-l-2 border-dashed"
          style={{ left: `${modelo.hojeLeftPct}%`, borderColor: "var(--g-today)" }}
        />
      )}
    </div>
  )
}
