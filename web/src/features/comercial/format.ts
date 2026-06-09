// Helpers locais do Comercial (mantém a feature autossuficiente).

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })

/** "R$ 1.234,56" (ou "—" se nulo). */
export function formatBRL(n: number | null | undefined): string {
  return n == null ? "—" : brl.format(n)
}

/** Lê um valor digitado (aceita "1.234,56", "1234.56", "R$ 1.200"); null se vazio/ inválido. */
export function parseValor(s: string): number | null {
  const limpo = s.replace(/[^\d.,-]/g, "").trim()
  if (!limpo) return null
  // BR: ponto = milhar, vírgula = decimal. Remove pontos e troca vírgula por ponto.
  const normal = limpo.replace(/\./g, "").replace(",", ".")
  const n = Number(normal)
  return Number.isFinite(n) ? n : null
}

/** "YYYY-MM-DD" de hoje (local). */
export function hojeISO(): string {
  const d = new Date()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  const dia = String(d.getDate()).padStart(2, "0")
  return `${d.getFullYear()}-${m}-${dia}`
}

/** "dd/mm/aa" (sem fuso — parse manual da string date). "" se nulo. */
export function formatData(iso: string | null): string {
  if (!iso) return ""
  const [y, m, d] = iso.split("-")
  return `${d}/${m}/${y.slice(2)}`
}

export type FollowupStatus = "atrasado" | "hoje" | "futuro"

/** Situação do próximo follow-up vs. hoje (p/ destacar o que está vencido/no dia). */
export function followupStatus(iso: string | null, hoje: string): FollowupStatus | null {
  if (!iso) return null
  if (iso < hoje) return "atrasado"
  if (iso === hoje) return "hoje"
  return "futuro"
}
