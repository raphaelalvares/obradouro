import { ChartGantt, ChevronLeft, Printer } from "lucide-react"
import { Link, useParams } from "react-router-dom"

import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { useChecklist } from "@/features/checklist/checklistApi"
import { formatBR, formatIntervalo } from "@/features/checklist/cronograma"
import { barraPos, montarGantt, type GanttModelo, type GanttRow } from "@/features/checklist/gantt"
import { useObra } from "@/features/obras/obrasApi"

// Paleta de DOCUMENTO (claro), independente do tema escuro do app — imprime em papel branco
// sem depender de "imprimir cor de fundo". Âmbar da marca (#D8A53A) nas barras.
const INK = "#1c1917"
const MUTE = "#78716c"
const LINE = "#e7e5e4"
const ETAPA_BAR = "#B07D1E"
const ETAPA_ROW = "#FBF6EA"
const TAREFA_BAR = "#E0B85A"
const PROGRESS = "rgba(0,0,0,0.24)"
const TODAY = "#C9952F"

const NOME_COL_PX = 200
const PX_POR_DIA = 16

function hojeISO(): string {
  const d = new Date()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  const dia = String(d.getDate()).padStart(2, "0")
  return `${d.getFullYear()}-${m}-${dia}`
}

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
          className="gantt-print overflow-hidden rounded-2xl border bg-white text-[13px]"
          style={{ borderColor: LINE, color: INK }}
        >
          <DocHeader
            titulo={obra.data?.nome ?? "Obra"}
            seq={obra.data?.seq_humano ?? null}
            modelo={modelo}
          />
          <Grafico modelo={modelo} />
          <div
            className="flex items-center justify-between px-5 py-3 text-[11px]"
            style={{ borderTop: `1px solid ${LINE}`, color: MUTE }}
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
    <div className="px-5 pt-5" style={{ borderBottom: `1px solid ${LINE}` }}>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.3em]" style={{ color: ETAPA_BAR }}>
            Obra #{seq ?? "—"} · Cronograma
          </div>
          <h1 className="font-display text-2xl font-light leading-tight" style={{ color: INK }}>
            {titulo}
          </h1>
        </div>
        <div className="text-right text-[11px]" style={{ color: MUTE }}>
          <div>
            {formatBR(modelo.min)} — {formatBR(modelo.max)}
          </div>
          <div>{modelo.totalDias} dias</div>
        </div>
      </div>
      <Legenda />
    </div>
  )
}

function Legenda() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 py-3 text-[11px]" style={{ color: MUTE }}>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-2 w-5 rounded-full" style={{ background: ETAPA_BAR }} /> Etapa
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-3 w-5 rounded-md" style={{ background: TAREFA_BAR }} /> Tarefa
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-3 w-5 rounded-md" style={{ background: TAREFA_BAR }}>
          <span className="block h-full w-1/2 rounded-l-md" style={{ background: PROGRESS }} />
        </span>
        Concluído
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="inline-block h-3 w-0 border-l-2 border-dashed" style={{ borderColor: TODAY }} />
        Hoje
      </span>
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
            <th className="sticky left-0 z-20 bg-white p-0" />
            <th className="p-0" style={{ borderBottom: `1px solid ${LINE}` }}>
              <div className="relative h-7">
                {modelo.meses.map((mes, i) => (
                  <div
                    key={i}
                    className="absolute top-0 truncate px-1.5 text-left text-[10px] font-normal uppercase tracking-wide"
                    style={{
                      left: `${mes.leftPct}%`,
                      width: `${mes.widthPct}%`,
                      color: MUTE,
                      borderLeft: i === 0 ? undefined : `1px solid ${LINE}`,
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
  const rowBg = etapa ? ETAPA_ROW : "#fff"
  const intervalo = formatIntervalo(row.inicio, row.fim)
  return (
    <tr className="gantt-row">
      <td
        className="sticky left-0 z-20 px-3 py-2 align-top"
        style={{ background: rowBg, borderBottom: `1px solid ${LINE}` }}
      >
        <div className="flex items-baseline gap-1.5">
          {row.seq != null && (
            <span className="shrink-0 font-display text-[11px]" style={{ color: MUTE }}>
              #{row.seq}
            </span>
          )}
          <span
            className={`break-words ${etapa ? "text-[13px] font-semibold" : "pl-1 text-[12px]"}`}
            style={{ color: etapa ? INK : "#44403c" }}
          >
            {row.nome}
          </span>
        </div>
      </td>

      <td className="p-0" style={{ background: rowBg, borderBottom: `1px solid ${LINE}` }}>
        <div className="relative min-h-[2.25rem]">
          <Grade modelo={modelo} />
          {pos && (
            <div
              className={`absolute top-1/2 -translate-y-1/2 overflow-hidden ${etapa ? "h-2 rounded-full" : "h-3.5 rounded-md"}`}
              title={intervalo}
              style={{
                left: `${pos.leftPct}%`,
                width: `${pos.widthPct}%`,
                minWidth: 3,
                background: etapa ? ETAPA_BAR : TAREFA_BAR,
                boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.08)",
              }}
            >
              {row.progresso != null && row.progresso > 0 && (
                <div
                  className="h-full"
                  style={{ width: `${Math.min(100, row.progresso * 100)}%`, background: PROGRESS }}
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
      {modelo.meses.map((mes, i) =>
        i === 0 ? null : (
          <div
            key={i}
            className="absolute inset-y-0"
            style={{ left: `${mes.leftPct}%`, borderLeft: `1px solid ${LINE}` }}
          />
        ),
      )}
      {modelo.hojeLeftPct != null && (
        <div
          className="absolute inset-y-0 border-l-2 border-dashed"
          style={{ left: `${modelo.hojeLeftPct}%`, borderColor: TODAY }}
        />
      )}
    </div>
  )
}
