import { type ReactNode } from "react"

import { Input } from "@/components/ui/input"
import { brl, parseNum } from "@/lib/num"
import type { CustoForm } from "@/features/checklist/checklistApi"

/** Estado (strings, p/ digitação BR) dos campos de custo de um nível-folha. */
export interface CamposCustoValue {
  unidade: string
  quantidade: string
  valorUnitario: string
  mo: string
  total: string // override: só vale quando totalTocado
  totalTocado: boolean
}

export const custoVazio: CamposCustoValue = {
  unidade: "",
  quantidade: "",
  valorUnitario: "",
  mo: "",
  total: "",
  totalTocado: false,
}

const round2 = (n: number) => Math.round(n * 100) / 100
const fmtNum = (n: number) => String(n).replace(".", ",")

/** Material derivado (quantidade × valor unitário) — null se faltar algum. */
function materialDe(v: CamposCustoValue): number | null {
  const q = parseNum(v.quantidade)
  const u = parseNum(v.valorUnitario)
  return q != null && u != null ? round2(q * u) : null
}

/** Total efetivo: override (se o usuário tocou no campo) senão MO + material. */
function totalDe(v: CamposCustoValue): number | null {
  if (v.totalTocado) return parseNum(v.total)
  const mo = parseNum(v.mo)
  const mat = materialDe(v)
  if (mo == null && mat == null) return null
  return round2((mo ?? 0) + (mat ?? 0))
}

/** Payload p/ o backend (não envia custo_material; o backend deriva). */
export function camposCustoToForm(v: CamposCustoValue): CustoForm {
  return {
    unidade: v.unidade.trim() || null,
    quantidade: parseNum(v.quantidade),
    valor_unitario: parseNum(v.valorUnitario),
    custo_mao_obra: parseNum(v.mo),
    custo_total: totalDe(v),
  }
}

/** true se algum campo de custo foi preenchido (decide se manda o bloco / se há custo a mover). */
export function temCusto(v: CamposCustoValue): boolean {
  return !!(
    v.unidade.trim() ||
    v.quantidade.trim() ||
    v.valorUnitario.trim() ||
    v.mo.trim() ||
    (v.totalTocado && v.total.trim())
  )
}

/** Carrega os campos a partir dos valores numéricos do servidor (ao editar uma folha custeada). */
export function camposCustoDe(d: {
  unidade?: string | null
  quantidade?: number | null
  valor_unitario?: number | null
  custo_mao_obra?: number | null
  custo_total?: number | null
}): CamposCustoValue {
  const s = (n: number | null | undefined) => (n == null ? "" : fmtNum(n))
  // total é override quando NÃO bate com MO + (qtd × unit) — preserva totais legados/verba digitados.
  const mat = d.quantidade != null && d.valor_unitario != null ? d.quantidade * d.valor_unitario : null
  const auto = d.custo_mao_obra != null || mat != null ? (d.custo_mao_obra ?? 0) + (mat ?? 0) : null
  const tocado = d.custo_total != null && (auto == null || Math.abs(d.custo_total - auto) > 0.005)
  return {
    unidade: d.unidade ?? "",
    quantidade: s(d.quantidade),
    valorUnitario: s(d.valor_unitario),
    mo: s(d.custo_mao_obra),
    total: s(d.custo_total),
    totalTocado: tocado,
  }
}

/** Bloco reutilizável de custo (metragem × unitário + MO, com total calculado e sobrescrevível). */
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
  const total = totalDe(value)
  const set = (patch: Partial<CamposCustoValue>) => onChange({ ...value, ...patch })
  const totalMostrado = value.totalTocado ? value.total : total != null ? fmtNum(total) : ""
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
            onChange={(e) => set({ quantidade: e.target.value })}
            inputMode="decimal"
            placeholder="0"
          />
        </Campo>
        <Campo label="Valor unit.">
          <Input
            value={value.valorUnitario}
            onChange={(e) => set({ valorUnitario: e.target.value })}
            inputMode="decimal"
            placeholder="R$"
          />
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
        <Campo label="Mão de obra">
          <Input
            value={value.mo}
            onChange={(e) => set({ mo: e.target.value })}
            inputMode="decimal"
            placeholder="R$"
          />
        </Campo>
        <Campo label="Total">
          <Input
            value={totalMostrado}
            onChange={(e) => set({ total: e.target.value, totalTocado: e.target.value.trim() !== "" })}
            inputMode="decimal"
            placeholder="R$"
          />
        </Campo>
      </div>
      <p className="text-[11px] leading-snug text-muted-foreground">
        Material {material != null ? brl(material) : "—"} (qtd × unit.) + mão de obra ={" "}
        <span className="text-foreground">{total != null ? brl(total) : "—"}</span>.
        {value.totalTocado && " Total sobrescrito — limpe o campo p/ voltar ao cálculo."}
      </p>
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
