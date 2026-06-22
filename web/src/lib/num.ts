/** Parsing/formatação numérica BR compartilhados (custo/metragem). */

/** Aceita "1.234,56" (BR), "1234.56" ou "" → number | null (vazio limpa o campo). */
export function parseNum(s: string): number | null {
  const t = s.trim()
  if (!t) return null
  // com vírgula = decimal BR (ponto é milhar); sem vírgula = ponto já é o decimal.
  const norm = t.includes(",") ? t.replace(/\./g, "").replace(",", ".") : t
  const n = Number(norm)
  return Number.isFinite(n) ? n : null
}

/** R$ sem centavos (espelha o cronograma): 5000 → "R$ 5.000". */
export function brl(n: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  }).format(n)
}
