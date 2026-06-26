import { Pencil, Plus, RefreshCw, Search, ShieldX } from "lucide-react"
import { useMemo, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Input } from "@/components/ui/input"
import { CenteredSpinner, ErrorState } from "@/components/feedback/states"
import { brl } from "@/lib/num"
import { cn } from "@/lib/utils"

import {
  diasRestantes,
  ehPagante,
  useAdminMetricas,
  useAdminPlanos,
  useAdminTenants,
  useRenovarPlano,
  useRevogarPlano,
  type PlanoCatalogo,
  type TenantAdmin,
} from "./adminApi"
import { DefinirPlanoDialog } from "./DefinirPlanoDialog"
import { PlanoCatalogoDialog } from "./PlanoCatalogoDialog"

type Aba = "clientes" | "planos"

export function AdminPage() {
  const [aba, setAba] = useState<Aba>("clientes")
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
        </div>
      </div>
      {aba === "clientes" ? <ClientesTab /> : <PlanosTab />}
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
  const planos = useAdminPlanos()
  const renovar = useRenovarPlano()
  const revogar = useRevogarPlano()

  const [busca, setBusca] = useState("")
  const [definir, setDefinir] = useState<TenantAdmin | null>(null)
  const [aRevogar, setARevogar] = useState<TenantAdmin | null>(null)

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
      {/* métricas */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Metrica titulo="Clientes" valor={m ? String(m.total_clientes) : "—"} />
        <Metrica titulo="Pagantes" valor={m ? String(m.pagantes) : "—"} />
        <Metrica
          titulo="Receita/mês (est.)"
          valor={m ? brl(m.receita_mensal_estimada) : "—"}
        />
        <Metrica titulo="Vencem em 7d" valor={m ? String(m.expirando_7d) : "—"} />
        <Metrica titulo="Vencem em 30d" valor={m ? String(m.expirando_30d) : "—"} />
      </div>

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
        <table className="w-full min-w-[820px] text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted-foreground">
              <th className="px-4 py-3 font-medium">Cliente</th>
              <th className="px-4 py-3 font-medium">Plano</th>
              <th className="px-4 py-3 font-medium">Validade</th>
              <th className="px-4 py-3 font-medium">Uso</th>
              <th className="px-4 py-3 font-medium">Cadastro</th>
              <th className="px-4 py-3 text-right font-medium">Ações</th>
            </tr>
          </thead>
          <tbody>
            {filtrados.map((t) => (
              <LinhaTenant
                key={t.tenant_id}
                t={t}
                onDefinir={() => setDefinir(t)}
                onRenovar={() => renovar.mutate({ tenantId: t.tenant_id, meses: 1 })}
                renovando={renovar.isPending && renovar.variables?.tenantId === t.tenant_id}
                onRevogar={() => setARevogar(t)}
              />
            ))}
            {filtrados.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                  Nenhum cliente encontrado.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>

      <DefinirPlanoDialog
        open={definir !== null}
        onOpenChange={(o) => !o && setDefinir(null)}
        tenant={definir}
        planos={planos.data ?? []}
      />
      <ConfirmDialog
        open={aRevogar !== null}
        onOpenChange={(o) => !o && setARevogar(null)}
        title="Revogar licença?"
        description={
          aRevogar
            ? `${aRevogar.nome_escritorio || aRevogar.nome || aRevogar.email} volta para o plano free imediatamente.`
            : undefined
        }
        confirmLabel="Revogar"
        pending={revogar.isPending}
        onConfirm={() =>
          aRevogar &&
          revogar.mutate(aRevogar.tenant_id, { onSuccess: () => setARevogar(null) })
        }
      />
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

function fmtArmazenamento(bytes: number): string {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  return `${Math.round(bytes / 1024 / 1024)} MB`
}

function LinhaTenant({
  t,
  onDefinir,
  onRenovar,
  renovando,
  onRevogar,
}: {
  t: TenantAdmin
  onDefinir: () => void
  onRenovar: () => void
  renovando: boolean
  onRevogar: () => void
}) {
  const pagante = ehPagante(t)
  const dias = diasRestantes(t)
  return (
    <tr className="border-b border-border/60 last:border-0">
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
        <div>{t.obras_ativas} obra(s)</div>
        <div className="text-xs">{fmtArmazenamento(t.armazenamento_bytes)}</div>
      </td>
      <td className="px-4 py-3 text-muted-foreground">
        {new Date(t.created_at).toLocaleDateString("pt-BR")}
      </td>
      <td className="px-4 py-3">
        <div className="flex justify-end gap-1.5">
          <Button size="sm" variant="outline" onClick={onDefinir}>
            <Pencil className="size-3.5" /> Plano
          </Button>
          {pagante && (
            <>
              <Button size="sm" variant="ghost" disabled={renovando} onClick={onRenovar} title="Renovar +1 mês">
                <RefreshCw className={cn("size-3.5", renovando && "animate-spin")} />
              </Button>
              <Button size="sm" variant="ghost" onClick={onRevogar} title="Revogar">
                <ShieldX className="size-3.5 text-destructive" />
              </Button>
            </>
          )}
        </div>
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
