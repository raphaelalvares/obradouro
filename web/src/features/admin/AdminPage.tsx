import { Pencil, Plus, Search } from "lucide-react"
import { useEffect, useMemo, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { CenteredSpinner, ErrorState } from "@/components/feedback/states"
import { brl, brlCentavos, fmtBytes, fmtMb } from "@/lib/num"
import { cn } from "@/lib/utils"

import {
  diasRestantes,
  ehPagante,
  tempoRelativo,
  useAdminMetricas,
  useAdminPlanos,
  useAdminTenants,
  useArmazenamentoResumo,
  useMarcarVistos,
  type PlanoCatalogo,
  type TenantAdmin,
} from "./adminApi"
import { AtividadeTab } from "./AtividadeTab"
import { PlanoCatalogoDialog } from "./PlanoCatalogoDialog"
import { TenantDetalheDrawer } from "./TenantDetalheDrawer"

type Aba = "clientes" | "planos" | "atividade"

export function AdminPage() {
  const [aba, setAba] = useState<Aba>("clientes")
  const marcarVistos = useMarcarVistos()

  // ao abrir o painel, zera o contador de "novos cadastros" (badge no AppShell)
  useEffect(() => {
    marcarVistos.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="font-word text-3xl">Admin</h1>
        <div className="flex gap-1 rounded-xl border border-border p-1">
          <AbaBtn ativa={aba === "clientes"} onClick={() => setAba("clientes")}>
            Clientes
          </AbaBtn>
          <AbaBtn ativa={aba === "planos"} onClick={() => setAba("planos")}>
            Planos
          </AbaBtn>
          <AbaBtn ativa={aba === "atividade"} onClick={() => setAba("atividade")}>
            Atividade
          </AbaBtn>
        </div>
      </div>
      {aba === "clientes" ? <ClientesTab /> : aba === "planos" ? <PlanosTab /> : <AtividadeTab />}
    </div>
  )
}

function AbaBtn({
  ativa,
  onClick,
  children,
}: {
  ativa: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
        ativa ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  )
}

// ============================================================ Clientes
function ClientesTab() {
  const tenants = useAdminTenants()
  const metricas = useAdminMetricas()

  const [busca, setBusca] = useState("")
  const [detalhe, setDetalhe] = useState<TenantAdmin | null>(null)

  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase()
    const lista = tenants.data ?? []
    if (!q) return lista
    return lista.filter((t) =>
      [t.email, t.nome, t.nome_escritorio].some((s) => s?.toLowerCase().includes(q)),
    )
  }, [tenants.data, busca])

  if (tenants.isLoading) return <CenteredSpinner />
  if (tenants.isError)
    return <ErrorState message="Não foi possível carregar os clientes." onRetry={() => tenants.refetch()} />

  const m = metricas.data

  return (
    <div className="flex flex-col gap-5">
      {/* métricas / analytics */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        <Metrica titulo="Clientes" valor={m ? String(m.total_clientes) : "—"} />
        <Metrica titulo="Pagantes" valor={m ? String(m.pagantes) : "—"} />
        <Metrica titulo="MRR (est.)" valor={m ? brl(m.receita_mensal_estimada) : "—"} />
        <Metrica titulo="Novos no mês" valor={m ? String(m.novos_mes) : "—"} />
        <Metrica titulo="Churn 30d" valor={m ? String(m.churn_30d) : "—"} />
        <Metrica titulo="Vencem em 7d" valor={m ? String(m.expirando_7d) : "—"} />
      </div>

      {/* pool de armazenamento (Drive) */}
      <ArmazenamentoPanel />

      {/* busca */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar por email, nome ou escritório…"
          className="pl-9"
        />
      </div>

      {/* tabela */}
      <Card className="overflow-x-auto">
        <table className="w-full min-w-[960px] text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-3 font-medium">Cliente</th>
              <th className="px-4 py-3 font-medium">Plano</th>
              <th className="px-4 py-3 font-medium">Validade</th>
              <th className="px-4 py-3 font-medium">Último pagto</th>
              <th className="px-4 py-3 font-medium">Atividade</th>
              <th className="px-4 py-3 font-medium">Uso</th>
              <th className="px-4 py-3 font-medium">Cliente desde</th>
            </tr>
          </thead>
          <tbody>
            {filtrados.map((t) => (
              <LinhaTenant key={t.tenant_id} t={t} onAbrir={() => setDetalhe(t)} />
            ))}
            {filtrados.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-muted-foreground">
                  Nenhum cliente encontrado.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <TenantDetalheDrawer tenant={detalhe} onOpenChange={(o) => !o && setDetalhe(null)} />
    </div>
  )
}

function Metrica({ titulo, valor }: { titulo: string; valor: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs uppercase tracking-wider text-muted-foreground">{titulo}</p>
      <p className="mt-1 text-2xl font-semibold">{valor}</p>
    </Card>
  )
}

// ---------------------------------------------------------------- pool de armazenamento (Drive)
function BarraArmaz({ pct, tone }: { pct: number; tone: "fisico" | "reserva" | "over" }) {
  const cor = tone === "over" ? "bg-destructive" : tone === "fisico" ? "bg-primary" : "bg-amber-500"
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
      <div className={cn("h-full rounded-full", cor)} style={{ width: `${Math.max(0, pct)}%` }} />
    </div>
  )
}

function ArmazenamentoPanel() {
  const r = useArmazenamentoResumo()
  const d = r.data
  if (r.isLoading) return <Card className="p-4"><CenteredSpinner className="py-4" /></Card>
  if (r.isError || !d) return null // silencioso: nunca bloqueia a aba de clientes

  const MB = 1024 * 1024
  const total = d.total_bytes
  const comprometidoBytes = d.comprometido_mb * MB
  const pctFisico =
    total && d.usado_real_bytes != null ? (d.usado_real_bytes / total) * 100 : 0
  const pctReserva = total ? (comprometidoBytes / total) * 100 : 0

  return (
    <Card className="flex flex-col gap-4 p-5">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="font-medium">Armazenamento</h2>
          <p className="text-xs text-muted-foreground">
            Espaço físico real do Drive × cotas prometidas aos clientes.
          </p>
        </div>
        <span className="rounded bg-muted px-2 py-0.5 text-[11px] uppercase tracking-wide text-muted-foreground">
          {d.backend}
        </span>
      </div>

      {d.overcommit && (
        <div className="rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
          Você prometeu mais espaço ({fmtMb(d.comprometido_mb)}) do que cabe fisicamente
          {total != null ? ` (${fmtBytes(total)})` : ""}. Reduza alocações ou aumente o pool.
        </div>
      )}

      {total != null ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <div className="mb-1 flex justify-between text-xs">
              <span className="text-muted-foreground">Físico (real no Drive)</span>
              <span className="font-medium">
                {d.usado_real_bytes != null ? fmtBytes(d.usado_real_bytes) : "—"} de {fmtBytes(total)}
              </span>
            </div>
            <BarraArmaz pct={pctFisico} tone="fisico" />
            <div className="mt-1 text-xs text-muted-foreground">
              {d.usado_real_bytes != null ? `${fmtBytes(total - d.usado_real_bytes)} livres` : ""}
              {d.lixeira_bytes ? ` · lixeira ${fmtBytes(d.lixeira_bytes)}` : ""}
            </div>
          </div>
          <div>
            <div className="mb-1 flex justify-between text-xs">
              <span className="text-muted-foreground">Comprometido (reservado)</span>
              <span className="font-medium">
                {fmtMb(d.comprometido_mb)} de {fmtBytes(total)}
              </span>
            </div>
            <BarraArmaz pct={pctReserva} tone={d.overcommit ? "over" : "reserva"} />
            <div className="mt-1 text-xs text-muted-foreground">
              {d.livre_para_alocar_bytes != null
                ? `${fmtBytes(d.livre_para_alocar_bytes)} livres p/ alocar`
                : ""}
            </div>
          </div>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">
          Espaço físico do Drive indisponível neste backend ({d.backend}). Comprometido:{" "}
          {fmtMb(d.comprometido_mb)}.
        </p>
      )}

      <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
        <span>
          Clientes: <b className="text-foreground">{d.n_clientes}</b>
        </span>
        <span>
          Consumo contabilizado:{" "}
          <b className="text-foreground">{fmtBytes(d.consumo_contabilizado_bytes)}</b>
        </span>
        <span>
          Reservado a pagantes: <b className="text-foreground">{fmtMb(d.comprometido_pagantes_mb)}</b>
        </span>
        {d.ilimitado_presente && (
          <span className="text-amber-600">há cliente com storage ilimitado</span>
        )}
      </div>
    </Card>
  )
}

/** Consumo contabilizado / limite efetivo (∞ = ilimitado). */
function usoLabel(bytes: number, limiteMb: number): string {
  const consumo = fmtBytes(bytes)
  return limiteMb < 0 ? `${consumo} / ∞` : `${consumo} / ${fmtMb(limiteMb)}`
}

function LinhaTenant({ t, onAbrir }: { t: TenantAdmin; onAbrir: () => void }) {
  const pagante = ehPagante(t)
  const dias = diasRestantes(t)
  return (
    <tr
      className="cursor-pointer border-b border-border/60 last:border-0 hover:bg-accent/50"
      onClick={onAbrir}
    >
      <td className="px-4 py-3">
        <div className="font-medium">{t.nome_escritorio || t.nome || "—"}</div>
        <div className="text-xs text-muted-foreground">{t.email}</div>
      </td>
      <td className="px-4 py-3">
        <PlanoBadge codigo={t.plano_codigo} nome={t.plano_nome} pagante={pagante} />
        {t.origem && pagante && (
          <div className="mt-0.5 text-[11px] uppercase tracking-wide text-muted-foreground">
            {t.origem}
          </div>
        )}
      </td>
      <td className="px-4 py-3">
        <Validade t={t} dias={dias} pagante={pagante} />
      </td>
      <td className="px-4 py-3 text-muted-foreground">
        {t.ultimo_pagamento_cents != null ? (
          <div>
            <div className="font-medium text-foreground">
              {brlCentavos(t.ultimo_pagamento_cents)}
            </div>
            <div className="text-xs">
              {t.ultimo_pagamento_em
                ? new Date(t.ultimo_pagamento_em).toLocaleDateString("pt-BR")
                : ""}
            </div>
          </div>
        ) : (
          "—"
        )}
      </td>
      <td className="px-4 py-3 text-muted-foreground">
        <div>
          <span className="text-xs uppercase tracking-wide">login</span>{" "}
          <span className="text-foreground">{tempoRelativo(t.ultimo_login)}</span>
        </div>
        <div className="text-xs">ação {tempoRelativo(t.ultima_atividade_em)}</div>
      </td>
      <td className="px-4 py-3 text-muted-foreground">
        <div>{t.obras_ativas} obra(s)</div>
        <div className="text-xs">{usoLabel(t.armazenamento_bytes, t.armazenamento_limite_mb)}</div>
      </td>
      <td className="px-4 py-3 text-muted-foreground">
        {new Date(t.created_at).toLocaleDateString("pt-BR")}
      </td>
    </tr>
  )
}

function PlanoBadge({
  codigo,
  nome,
  pagante,
}: {
  codigo: string
  nome: string
  pagante: boolean
}) {
  return (
    <span
      className={cn(
        "inline-flex rounded-md px-2 py-0.5 text-xs font-medium",
        pagante ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground",
      )}
    >
      {nome || codigo}
    </span>
  )
}

function Validade({
  t,
  dias,
  pagante,
}: {
  t: TenantAdmin
  dias: number | null
  pagante: boolean
}) {
  if (!pagante) return <span className="text-muted-foreground">—</span>
  if (dias === null) return <span className="text-muted-foreground">sem expiração</span>
  if (dias < 0)
    return <span className="font-medium text-destructive">expirada</span>
  return (
    <div>
      <span
        className={cn(
          "font-medium",
          dias <= 7 ? "text-destructive" : dias <= 30 ? "text-amber-600" : "text-foreground",
        )}
      >
        {dias} dia(s)
      </span>
      <div className="text-xs text-muted-foreground">
        {(() => {
          const fim = t.origem === "stripe" ? t.current_period_end : t.expira_em
          return fim ? new Date(fim).toLocaleDateString("pt-BR") : ""
        })()}
      </div>
    </div>
  )
}

// ============================================================ Planos (catálogo)
function PlanosTab() {
  const planos = useAdminPlanos()
  const [editar, setEditar] = useState<PlanoCatalogo | null>(null)
  const [criando, setCriando] = useState(false)

  if (planos.isLoading) return <CenteredSpinner />
  if (planos.isError)
    return <ErrorState message="Não foi possível carregar os planos." onRetry={() => planos.refetch()} />

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setCriando(true)}>
          <Plus className="size-4" /> Novo plano
        </Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {(planos.data ?? []).map((p) => (
          <Card key={p.codigo} className="flex flex-col gap-3 p-5">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-medium">{p.nome}</h3>
                  {!p.ativo && (
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                      inativo
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">{p.codigo}</p>
              </div>
              <div className="text-right">
                <div className="font-semibold">
                  {p.preco_mensal ? brl(p.preco_mensal) : "Grátis"}
                </div>
                <div className="text-xs text-muted-foreground">por mês</div>
                {p.preco_mensal && !p.stripe_price_id && (
                  <div className="text-[11px] text-amber-600">sem Stripe Price</div>
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5 text-xs text-muted-foreground">
              {Object.entries(p.limites).map(([k, v]) => (
                <span key={k} className="rounded bg-muted px-1.5 py-0.5">
                  {k}: {v === -1 ? "∞" : v}
                </span>
              ))}
              {Object.entries(p.flags)
                .filter(([, v]) => v)
                .map(([k]) => (
                  <span key={k} className="rounded bg-primary/10 px-1.5 py-0.5 text-primary">
                    {k}
                  </span>
                ))}
            </div>
            <Button size="sm" variant="outline" className="self-start" onClick={() => setEditar(p)}>
              <Pencil className="size-3.5" /> Editar
            </Button>
          </Card>
        ))}
      </div>

      <PlanoCatalogoDialog
        open={editar !== null}
        onOpenChange={(o) => !o && setEditar(null)}
        plano={editar}
      />
      <PlanoCatalogoDialog
        open={criando}
        onOpenChange={(o) => !o && setCriando(false)}
        plano={null}
      />
    </div>
  )
}
