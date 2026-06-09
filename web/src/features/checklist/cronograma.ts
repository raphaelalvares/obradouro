// Datas do cronograma: strings "YYYY-MM-DD" (date, sem hora; dias CORRIDOS, inclusivos).
// Toda a aritmética em UTC p/ não escorregar por fuso/horário de verão.

function toUTC(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number)
  return Date.UTC(y, m - 1, d)
}

function fromUTC(ms: number): string {
  const d = new Date(ms)
  const y = d.getUTCFullYear()
  const m = String(d.getUTCMonth() + 1).padStart(2, "0")
  const day = String(d.getUTCDate()).padStart(2, "0")
  return `${y}-${m}-${day}`
}

export function addDays(iso: string, n: number): string {
  return fromUTC(toUTC(iso) + n * 86_400_000)
}

/** dias inclusivos entre início e fim (mesmo dia = 1). */
export function duracaoDias(inicio: string, fim: string): number {
  return Math.round((toUTC(fim) - toUTC(inicio)) / 86_400_000) + 1
}

/** fim a partir de início + duração inclusiva (mínimo 1 dia). */
export function fimPorDuracao(inicio: string, dias: number): string {
  return addDays(inicio, Math.max(1, dias) - 1)
}

export function formatBR(iso: string | null): string {
  if (!iso) return "—"
  const [y, m, d] = iso.split("-")
  return `${d}/${m}/${y.slice(2)}`
}

/** "dd/mm – dd/mm" (string vazia se as duas faltam). */
export function formatIntervalo(inicio: string | null, fim: string | null): string {
  if (!inicio && !fim) return ""
  return `${formatBR(inicio)} – ${formatBR(fim)}`
}

export interface UnidadeBase {
  tipo: "item" | "etapa"
  id: string
  etapaId: string
  etapaNome: string
  label: string
}

export interface UnidadeCronograma extends UnidadeBase {
  inicio: string
  fim: string
  dias: number
}

/** Distribui [inicio .. inicio+totalDias-1] IGUALMENTE e EM SEQUÊNCIA entre as unidades (na ordem
 * recebida). O resto (totalDias % n) cai nas primeiras unidades. Cada unidade tem no mínimo 1 dia. */
export function distribuirIgual(
  unidades: UnidadeBase[],
  inicio: string,
  totalDias: number,
): UnidadeCronograma[] {
  const n = unidades.length
  if (n === 0) return []
  const base = Math.floor(totalDias / n)
  const rem = ((totalDias % n) + n) % n
  const out: UnidadeCronograma[] = []
  let cursor = inicio
  for (let i = 0; i < n; i++) {
    const dias = Math.max(1, base + (i < rem ? 1 : 0))
    const fim = fimPorDuracao(cursor, dias)
    out.push({ ...unidades[i], inicio: cursor, fim, dias })
    cursor = addDays(fim, 1)
  }
  return out
}
