import { formatData, hojeISO } from "@/features/comercial/format"
import type { Avanco } from "@/features/acompanhamento/acompanhamentoApi"

const GOLD = "#D8A53A" // planejado
const DONE = "#5FB87A" // realizado

// dias desde a epoch (UTC) p/ posicionar datas no eixo X sem fuso.
function dnum(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number)
  return Date.UTC(y, m - 1, d) / 86_400_000
}

const W = 600
const H = 220
const PAD_L = 34
const PAD_R = 12
const PAD_T = 12
const PAD_B = 26

/** Curva S: planejado (tracejado âmbar) × realizado (verde) ao longo do tempo. SVG responsivo. */
export function CurvaSChart({ avanco }: { avanco: Avanco }) {
  const { pontos, inicio, fim } = avanco
  if (!inicio || !fim || pontos.length < 2) {
    return (
      <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
        Sem cronograma suficiente para a curva. Defina datas nas tarefas (no Cronograma).
      </p>
    )
  }
  const d0 = dnum(inicio)
  const span = Math.max(1, dnum(fim) - d0)
  const x = (iso: string) => PAD_L + ((dnum(iso) - d0) / span) * (W - PAD_L - PAD_R)
  const y = (pct: number) => H - PAD_B - (Math.min(Math.max(pct, 0), 100) / 100) * (H - PAD_T - PAD_B)

  const linha = (sel: (p: (typeof pontos)[number]) => number) =>
    pontos.map((p) => `${x(p.data).toFixed(1)},${y(sel(p)).toFixed(1)}`).join(" ")

  const hoje = hojeISO()
  const hojeX = hoje >= inicio && hoje <= fim ? x(hoje) : null

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" preserveAspectRatio="none" role="img"
        aria-label="Curva S: planejado versus realizado">
        {/* grade horizontal 0/25/50/75/100 */}
        {[0, 25, 50, 75, 100].map((g) => (
          <g key={g}>
            <line
              x1={PAD_L}
              x2={W - PAD_R}
              y1={y(g)}
              y2={y(g)}
              stroke="hsl(var(--border))"
              strokeWidth={1}
            />
            <text x={PAD_L - 6} y={y(g) + 3} textAnchor="end" fontSize={9} fill="hsl(var(--muted-foreground))">
              {g}%
            </text>
          </g>
        ))}

        {/* hoje */}
        {hojeX != null && (
          <line
            x1={hojeX}
            x2={hojeX}
            y1={PAD_T}
            y2={H - PAD_B}
            stroke="hsl(var(--primary))"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        )}

        {/* planejado (tracejado) e realizado (sólido) */}
        <polyline points={linha((p) => p.planejado_pct)} fill="none" stroke={GOLD} strokeWidth={2} strokeDasharray="5 4" />
        <polyline points={linha((p) => p.real_pct)} fill="none" stroke={DONE} strokeWidth={2.5} />

        {/* rótulos de data nas pontas */}
        <text x={PAD_L} y={H - 8} textAnchor="start" fontSize={9} fill="hsl(var(--muted-foreground))">
          {formatData(inicio)}
        </text>
        <text x={W - PAD_R} y={H - 8} textAnchor="end" fontSize={9} fill="hsl(var(--muted-foreground))">
          {formatData(fim)}
        </text>
      </svg>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-5" style={{ background: GOLD }} /> Planejado
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-5" style={{ background: DONE }} /> Realizado
        </span>
        {hojeX != null && (
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-3 w-0 border-l border-dashed" style={{ borderColor: "hsl(var(--primary))" }} />
            Hoje
          </span>
        )}
      </div>
    </div>
  )
}
