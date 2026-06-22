import { useLayoutEffect, useRef, type ChangeEvent, type ReactNode } from "react"

import { Input } from "@/components/ui/input"
import { brl, fmtMoney, groupMoney, onlyDecimal, parseMoney, parseNum } from "@/lib/num"
import type { CustoForm } from "@/features/checklist/checklistApi"

/** Estado (strings, p/ digitação BR) dos campos de custo de um nível-folha. Composição UNITÁRIA:
 * material = qtd × material un.; mão de obra = qtd × M.O. un.; total = material + M.O. (sobrescrevível). */
export interface CamposCustoValue {
  unidade: string
  quantidade: string
  valorUnitario: string // R$/unidade do material
  moUnitaria: string // R$/unidade da mão de obra
  total: string // override: só vale quando totalTocado
  totalTocado: boolean
}

export const custoVazio: CamposCustoValue = {
  unidade: "",
  quantidade: "",
  valorUnitario: "",
  moUnitaria: "",
  total: "",
  totalTocado: false,
}

const round2 = (n: number) => Math.round(n * 100) / 100
const fmtNum = (n: number) => String(n).replace(".", ",")

/** Material TOTAL (quantidade × material unit.) — null se faltar algum. */
function materialDe(v: CamposCustoValue): number | null {
  const q = parseNum(v.quantidade)
  const u = parseMoney(v.valorUnitario)
  return q != null && u != null ? round2(q * u) : null
}

/** Mão de obra TOTAL (quantidade × M.O. unit.) — null se faltar algum. */
function moTotalDe(v: CamposCustoValue): number | null {
  const q = parseNum(v.quantidade)
  const u = parseMoney(v.moUnitaria)
  return q != null && u != null ? round2(q * u) : null
}

/** Total efetivo: override (se o usuário tocou no campo) senão material + mão de obra. */
function totalDe(v: CamposCustoValue): number | null {
  if (v.totalTocado) return parseMoney(v.total)
  const mat = materialDe(v)
  const mo = moTotalDe(v)
  if (mat == null && mo == null) return null
  return round2((mat ?? 0) + (mo ?? 0))
}

/** Payload p/ o backend: manda os UNITÁRIOS (o backend deriva material/MO/total). */
export function camposCustoToForm(v: CamposCustoValue): CustoForm {
  return {
    unidade: v.unidade.trim() || null,
    quantidade: parseNum(v.quantidade),
    valor_unitario: parseMoney(v.valorUnitario),
    mao_obra_unitaria: parseMoney(v.moUnitaria),
    custo_total: totalDe(v),
  }
}

/** true se algum campo de custo foi preenchido (decide se manda o bloco / se há custo a mover). */
export function temCusto(v: CamposCustoValue): boolean {
  return !!(
    v.unidade.trim() ||
    v.quantidade.trim() ||
    v.valorUnitario.trim() ||
    v.moUnitaria.trim() ||
    (v.totalTocado && v.total.trim())
  )
}

/** Carrega os campos a partir dos valores numéricos do servidor (ao editar uma folha custeada). */
export function camposCustoDe(d: {
  unidade?: string | null
  quantidade?: number | null
  valor_unitario?: number | null
  mao_obra_unitaria?: number | null
  custo_total?: number | null
}): CamposCustoValue {
  const sq = (n: number | null | undefined) => (n == null ? "" : fmtNum(n)) // quantidade (sem milhar)
  const sm = (n: number | null | undefined) => (n == null ? "" : fmtMoney(n)) // dinheiro (agrupado)
  // total é override quando NÃO bate com qtd × (material un. + M.O. un.) — preserva total digitado.
  const q = d.quantidade ?? null
  const mat = q != null && d.valor_unitario != null ? q * d.valor_unitario : null
  const mo = q != null && d.mao_obra_unitaria != null ? q * d.mao_obra_unitaria : null
  const auto = mat != null || mo != null ? (mat ?? 0) + (mo ?? 0) : null
  const tocado = d.custo_total != null && (auto == null || Math.abs(d.custo_total - auto) > 0.005)
  return {
    unidade: d.unidade ?? "",
    quantidade: sq(d.quantidade),
    valorUnitario: sm(d.valor_unitario),
    moUnitaria: sm(d.mao_obra_unitaria),
    total: sm(d.custo_total),
    totalTocado: tocado,
  }
}

/** Bloco reutilizável de custo por COMPOSIÇÃO UNITÁRIA: quantidade × (material un. + M.O. un.). O total
 * é calculado e sobrescrevível. */
export function CamposCusto({
  value,
  onChange,
  verba = true,
}: {
  value: CamposCustoValue
  onChange: (v: CamposCustoValue) => void
  /** mostra o atalho "Verba" (unidade=vb, qtd=1) — útil p/ valor fechado. */
  verba?: boolean
}) {
  const material = materialDe(value)
  const moTotal = moTotalDe(value)
  const total = totalDe(value)
  const set = (patch: Partial<CamposCustoValue>) => onChange({ ...value, ...patch })
  const totalMostrado = value.totalTocado ? value.total : total != null ? fmtMoney(total) : ""
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-3">
        <Campo label="Unidade">
          <Input
            value={value.unidade}
            onChange={(e) => set({ unidade: e.target.value })}
            maxLength={40}
            placeholder="m², un, vb…"
          />
        </Campo>
        <Campo label="Quantidade">
          <Input
            value={value.quantidade}
            onChange={(e) => set({ quantidade: onlyDecimal(e.target.value) })}
            inputMode="decimal"
            placeholder="0"
          />
        </Campo>
        <Campo label="Material (unit.)">
          <MoneyInput value={value.valorUnitario} onChange={(v) => set({ valorUnitario: v })} />
        </Campo>
      </div>
      {verba && (
        <button
          type="button"
          onClick={() => set({ unidade: "vb", quantidade: "1" })}
          className="text-xs text-primary transition-colors hover:underline"
        >
          Verba (valor fechado)
        </button>
      )}
      <div className="grid grid-cols-2 gap-3">
        <Campo label="Mão de obra (unit.)">
          <MoneyInput value={value.moUnitaria} onChange={(v) => set({ moUnitaria: v })} />
        </Campo>
        <Campo label="Total">
          <MoneyInput
            value={totalMostrado}
            onChange={(v) => set({ total: v, totalTocado: v.trim() !== "" })}
          />
        </Campo>
      </div>
      <p className="text-[11px] leading-snug text-muted-foreground">
        Material e M.O. são <span className="text-foreground">por unidade</span> (× quantidade):
        material {material != null ? brl(material) : "—"} + mão de obra{" "}
        {moTotal != null ? brl(moTotal) : "—"} ={" "}
        <span className="text-foreground">{total != null ? brl(total) : "—"}</span>.
        {value.totalTocado && " Total sobrescrito — limpe o campo p/ voltar ao cálculo."}
      </p>
    </div>
  )
}

/** Quantos dígitos há até a posição `end` (p/ preservar o cursor ao reagrupar). */
function digitosAte(s: string, end: number): number {
  let n = 0
  for (let i = 0; i < end && i < s.length; i++) if (s[i] >= "0" && s[i] <= "9") n++
  return n
}
/** Posição logo após o n-ésimo dígito (inverso de digitosAte). */
function aposDigitos(s: string, n: number): number {
  if (n <= 0) return 0
  let c = 0
  for (let i = 0; i < s.length; i++) {
    if (s[i] >= "0" && s[i] <= "9" && ++c >= n) return i + 1
  }
  return s.length
}

/** Campo de DINHEIRO: prefixo "R$" fixo + agrupamento de milhar ao vivo, digitação livre. Mantém o
 * cursor pela contagem de dígitos (reagrupar muda o comprimento → sem o ajuste o cursor pula pro fim). */
function MoneyInput({
  value,
  onChange,
}: {
  value: string
  onChange: (v: string) => void
}) {
  const ref = useRef<HTMLInputElement>(null)
  const cursor = useRef<number | null>(null)

  useLayoutEffect(() => {
    if (cursor.current != null && ref.current) {
      ref.current.setSelectionRange(cursor.current, cursor.current)
      cursor.current = null
    }
  })

  function handle(e: ChangeEvent<HTMLInputElement>) {
    const el = e.target
    const digitos = digitosAte(el.value, el.selectionStart ?? el.value.length)
    const next = groupMoney(el.value)
    cursor.current = aposDigitos(next, digitos)
    onChange(next)
  }

  return (
    <div className="relative">
      <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-base text-muted-foreground sm:text-sm">
        R$
      </span>
      <Input
        ref={ref}
        value={value}
        onChange={handle}
        inputMode="decimal"
        placeholder="0"
        className="pl-10"
      />
    </div>
  )
}

function Campo({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}
