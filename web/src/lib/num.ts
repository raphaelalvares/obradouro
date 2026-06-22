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

/** Dinheiro em BR-ESTRITO: ponto = milhar, vírgula = decimal. "1.234,56"→1234.56, "100.000"→100000.
 * (Diferente de parseNum, que trata ponto como decimal — aqui o campo SEMPRE vem agrupado.) */
export function parseMoney(s: string): number | null {
  const t = s.trim()
  if (!t) return null
  const n = Number(t.replace(/\./g, "").replace(",", "."))
  return Number.isFinite(n) ? n : null
}

/** Agrupa o que o usuário digita num campo de dinheiro: só dígitos + 1 vírgula (até 2 casas),
 * inteiro com separador de milhar. "100000"→"100.000", "1234,5"→"1.234,5", ""→"". */
export function groupMoney(raw: string): string {
  let s = raw.replace(/[^\d,]/g, "")
  const i = s.indexOf(",")
  if (i !== -1) s = s.slice(0, i + 1) + s.slice(i + 1).replace(/,/g, "").slice(0, 2)
  const [int, dec] = s.split(",")
  const grupos = int.replace(/^0+(?=\d)/, "").replace(/\B(?=(\d{3})+(?!\d))/g, ".")
  return dec !== undefined ? `${grupos},${dec}` : grupos
}

/** Número agrupado p/ preencher um campo de dinheiro a partir do servidor: 100000 → "100.000". */
export function fmtMoney(n: number): string {
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 }).format(n)
}
