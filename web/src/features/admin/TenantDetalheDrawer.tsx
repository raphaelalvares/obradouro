import {
  Ban,
  KeyRound,
  Loader2,
  Mail,
  Pencil,
  Plus,
  RefreshCw,
  ShieldCheck,
  ShieldX,
  Trash2,
} from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { CenteredSpinner } from "@/components/feedback/states"
import { Input } from "@/components/ui/input"
import { brlCentavos } from "@/lib/num"
import { cn } from "@/lib/utils"

import {
  diasRestantes,
  ehPagante,
  fimVigencia,
  useAdminAcessos,
  useAdminPlanos,
  useAutorizarAcesso,
  useCriarNota,
  useExcluirNota,
  useNotas,
  useRenovarPlano,
  useRevogarPlano,
  useRevogarAcesso,
  useSuporteAcao,
  useSuporteStatus,
  useTenantHistorico,
  type HistoricoPlano,
  type TenantAdmin,
} from "./adminApi"
import { DefinirPlanoDialog } from "./DefinirPlanoDialog"

const fmt = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" })
function data(iso: string | null | undefined): string {
  return iso ? fmt.format(new Date(iso)) : "—"
}

// motivo cru (do banco) → rótulo amigável na timeline.
const MOTIVO: Record<string, string> = {
  checkout: "assinou",
  active: "ativo",
  trialing: "trial",
  past_due: "pagamento pendente",
  canceled: "cancelou",
  unpaid: "não pagou",
  admin_cortesia: "cortesia (admin)",
  admin_renovou: "renovado (admin)",
  admin_revogou: "revogado (admin)",
}

export function TenantDetalheDrawer({
  tenant,
  onOpenChange,
}: {
  tenant: TenantAdmin | null
  onOpenChange: (open: boolean) => void
}) {
  const hist = useTenantHistorico(tenant?.tenant_id ?? null)
  const planos = useAdminPlanos()
  const renovar = useRenovarPlano()
  const revogar = useRevogarPlano()
  const [cortesia, setCortesia] = useState(false)
  const [aRevogar, setARevogar] = useState(false)

  if (!tenant) return null
  const pagante = ehPagante(tenant)
  const dias = diasRestantes(tenant)
  const venc = fimVigencia(tenant)

  return (
    <Dialog open={tenant !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{tenant.nome_escritorio || tenant.nome || tenant.email}</DialogTitle>
          <p className="text-sm text-muted-foreground">{tenant.email}</p>
        </DialogHeader>

        <div className="flex flex-col gap-5">
          {/* resumo */}
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Resumo titulo="Plano" valor={tenant.plano_nome} sub={tenant.origem ?? "free"} />
            <Resumo
              titulo="Vencimento"
              valor={pagante ? (dias === null ? "sem expiração" : `${dias} dia(s)`) : "—"}
              sub={venc ? data(venc) : ""}
            />
            <Resumo titulo="Cliente desde" valor={data(tenant.created_at)} />
            <Resumo
              titulo="Último pagamento"
              valor={
                tenant.ultimo_pagamento_cents != null
                  ? brlCentavos(tenant.ultimo_pagamento_cents)
                  : "—"
              }
              sub={tenant.ultimo_pagamento_em ? data(tenant.ultimo_pagamento_em) : ""}
            />
          </section>

          {/* cortesia / trial (override manual — o caminho normal é o Stripe) */}
          <section className="rounded-xl border border-border p-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <div className="text-sm font-medium">Cortesia / trial</div>
                <p className="text-xs text-muted-foreground">
                  Liberar plano à mão (exceção — o normal é o cliente assinar no Stripe).
                </p>
              </div>
              <div className="flex gap-1.5">
                <Button size="sm" variant="outline" onClick={() => setCortesia(true)}>
                  <Pencil className="size-3.5" /> Conceder
                </Button>
                {pagante && (
                  <>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={renovar.isPending}
                      title="Renovar +1 mês"
                      onClick={() => renovar.mutate({ tenantId: tenant.tenant_id, meses: 1 })}
                    >
                      <RefreshCw className={cn("size-3.5", renovar.isPending && "animate-spin")} />
                    </Button>
                    <Button size="sm" variant="ghost" title="Revogar" onClick={() => setARevogar(true)}>
                      <ShieldX className="size-3.5 text-destructive" />
                    </Button>
                  </>
                )}
              </div>
            </div>
          </section>

          {/* timeline de planos + pagamentos */}
          {hist.isLoading ? (
            <CenteredSpinner className="py-6" />
          ) : (
            <div className="grid gap-5 sm:grid-cols-2">
              <section>
                <h3 className="mb-2 text-xs uppercase tracking-wider text-muted-foreground">
                  Épocas de plano
                </h3>
                {hist.data?.historico.length ? (
                  <ul className="space-y-1.5">
                    {hist.data.historico.map((h, i) => (
                      <TimelineItem key={i} h={h} />
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">Sem histórico ainda.</p>
                )}
              </section>

              <section>
                <h3 className="mb-2 text-xs uppercase tracking-wider text-muted-foreground">
                  Pagamentos
                </h3>
                {hist.data?.pagamentos.length ? (
                  <ul className="space-y-1.5">
                    {hist.data.pagamentos.map((p, i) => (
                      <li
                        key={i}
                        className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2 text-sm"
                      >
                        <span className="font-medium">{brlCentavos(p.valor_cents)}</span>
                        <span className="text-xs text-muted-foreground">{data(p.pago_em)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-muted-foreground">Nenhum pagamento registrado.</p>
                )}
              </section>
            </div>
          )}

          <AcessosSection tenantId={tenant.tenant_id} />
          <SuporteSection tenantId={tenant.tenant_id} />
          <NotasSection tenantId={tenant.tenant_id} />
        </div>
      </DialogContent>

      <DefinirPlanoDialog
        open={cortesia}
        onOpenChange={setCortesia}
        tenant={tenant}
        planos={planos.data ?? []}
      />
      <ConfirmDialog
        open={aRevogar}
        onOpenChange={setARevogar}
        title="Revogar licença?"
        description={`${tenant.nome_escritorio || tenant.nome || tenant.email} volta para o plano free imediatamente.`}
        confirmLabel="Revogar"
        pending={revogar.isPending}
        onConfirm={() =>
          revogar.mutate(tenant.tenant_id, { onSuccess: () => setARevogar(false) })
        }
      />
    </Dialog>
  )
}

function Resumo({ titulo, valor, sub }: { titulo: string; valor: string; sub?: string }) {
  return (
    <div className="rounded-xl border border-border p-3">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{titulo}</div>
      <div className="mt-0.5 text-sm font-medium capitalize">{valor}</div>
      {sub ? <div className="text-xs text-muted-foreground">{sub}</div> : null}
    </div>
  )
}

// ---------------------------------------------------------------- clientes nas obras
function AcessosSection({ tenantId }: { tenantId: string }) {
  const acessos = useAdminAcessos(tenantId)
  const autorizar = useAutorizarAcesso(tenantId)
  const revogar = useRevogarAcesso(tenantId)
  const [alvo, setAlvo] = useState("")
  const [email, setEmail] = useState("")

  const alvos = acessos.data?.alvos ?? []
  function convidar() {
    const a = alvos.find((x) => `${x.tipo}:${x.id}` === alvo)
    if (!a || !email.trim()) return
    autorizar.mutate(
      {
        projeto_id: a.tipo === "projeto" ? a.id : null,
        obra_id: a.tipo === "obra" ? a.id : null,
        email: email.trim(),
      },
      { onSuccess: () => setEmail("") },
    )
  }

  return (
    <section className="rounded-xl border border-border p-3">
      <div className="text-sm font-medium">Clientes nas obras</div>
      <p className="mb-2 text-xs text-muted-foreground">
        E-mails autorizados no portal do cliente (ajuda sem entrar na conta dele).
      </p>

      {acessos.isLoading ? (
        <CenteredSpinner className="py-4" />
      ) : acessos.data?.acessos.length ? (
        <ul className="mb-3 space-y-1.5">
          {acessos.data.acessos.map((ac) => (
            <li
              key={ac.id}
              className="flex items-center justify-between gap-2 rounded-lg border border-border/60 px-3 py-2 text-sm"
            >
              <div className="min-w-0">
                <div className="truncate">{ac.email}</div>
                <div className="text-xs text-muted-foreground">
                  {ac.alvo_nome ?? "—"} ·{" "}
                  <span className={ac.cadastrado ? "text-primary" : ""}>
                    {ac.cadastrado ? "entrou" : "aguardando cadastro"}
                  </span>
                </div>
              </div>
              <Button
                size="icon"
                variant="ghost"
                className="size-8 shrink-0"
                title="Revogar acesso"
                disabled={revogar.isPending}
                onClick={() => revogar.mutate(ac.id)}
              >
                <Trash2 className="size-3.5 text-destructive" />
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mb-3 text-sm text-muted-foreground">Nenhum cliente autorizado.</p>
      )}

      {/* convidar */}
      {alvos.length > 0 ? (
        <div className="flex flex-col gap-2 sm:flex-row">
          <select
            value={alvo}
            onChange={(e) => setAlvo(e.target.value)}
            className="h-10 rounded-xl border border-input bg-card px-3 text-sm sm:w-44"
          >
            <option value="">Obra/projeto…</option>
            {alvos.map((a) => (
              <option key={`${a.tipo}:${a.id}`} value={`${a.tipo}:${a.id}`}>
                {a.tipo === "obra" ? "🏗 " : "📐 "}
                {a.nome}
              </option>
            ))}
          </select>
          <Input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email@cliente.com"
            className="flex-1"
          />
          <Button onClick={convidar} disabled={!alvo || !email.trim() || autorizar.isPending}>
            {autorizar.isPending ? <Loader2 className="animate-spin" /> : <Plus className="size-4" />}
            Convidar
          </Button>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">Este cliente ainda não tem obras/projetos.</p>
      )}
    </section>
  )
}

// ---------------------------------------------------------------- suporte (GoTrue)
function SuporteSection({ tenantId }: { tenantId: string }) {
  const status = useSuporteStatus(tenantId)
  const { reenviar, resetSenha, suspender, reativar } = useSuporteAcao(tenantId)

  async function gerarReset() {
    const r = await resetSenha.mutateAsync()
    if (r.link) {
      try {
        await navigator.clipboard.writeText(r.link)
        toast.success("Link de redefinição copiado", { description: "Envie ao usuário." })
      } catch {
        toast.message("Link de redefinição gerado", { description: r.link })
      }
    }
  }

  if (status.isError) {
    return (
      <section className="rounded-xl border border-border p-3">
        <div className="text-sm font-medium">Suporte</div>
        <p className="text-xs text-muted-foreground">Auth não configurada — ações indisponíveis.</p>
      </section>
    )
  }

  const s = status.data
  return (
    <section className="rounded-xl border border-border p-3">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium">Suporte</div>
        {s && (
          <div className="flex items-center gap-2 text-xs">
            <span className={s.email_confirmado ? "text-primary" : "text-amber-600"}>
              {s.email_confirmado ? "e-mail confirmado" : "e-mail não confirmado"}
            </span>
            {s.banido && <span className="text-destructive">· suspenso</span>}
          </div>
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <Button
          size="sm"
          variant="outline"
          disabled={reenviar.isPending || s?.email_confirmado}
          onClick={() =>
            reenviar.mutate(undefined, {
              onSuccess: () => toast.success("Confirmação reenviada"),
              onError: () => toast.error("Não foi possível reenviar"),
            })
          }
        >
          <Mail className="size-3.5" /> Reenviar confirmação
        </Button>
        <Button size="sm" variant="outline" disabled={resetSenha.isPending} onClick={gerarReset}>
          <KeyRound className="size-3.5" /> Link de reset
        </Button>
        {s?.banido ? (
          <Button
            size="sm"
            variant="outline"
            disabled={reativar.isPending}
            onClick={() =>
              reativar.mutate(undefined, { onSuccess: () => toast.success("Conta reativada") })
            }
          >
            <ShieldCheck className="size-3.5" /> Reativar
          </Button>
        ) : (
          <Button
            size="sm"
            variant="outline"
            disabled={suspender.isPending}
            onClick={() =>
              suspender.mutate(undefined, { onSuccess: () => toast.success("Conta suspensa") })
            }
          >
            <Ban className="size-3.5 text-destructive" /> Suspender
          </Button>
        )}
      </div>
    </section>
  )
}

// ---------------------------------------------------------------- notas internas
function NotasSection({ tenantId }: { tenantId: string }) {
  const notas = useNotas(tenantId)
  const criar = useCriarNota(tenantId)
  const excluir = useExcluirNota(tenantId)
  const [texto, setTexto] = useState("")

  function adicionar() {
    if (!texto.trim()) return
    criar.mutate(texto.trim(), { onSuccess: () => setTexto("") })
  }

  return (
    <section className="rounded-xl border border-border p-3">
      <div className="text-sm font-medium">Notas internas</div>
      <p className="mb-2 text-xs text-muted-foreground">Só você (admin) vê.</p>
      {notas.data?.length ? (
        <ul className="mb-3 space-y-1.5">
          {notas.data.map((n) => (
            <li
              key={n.id}
              className="flex items-start justify-between gap-2 rounded-lg border border-border/60 px-3 py-2 text-sm"
            >
              <div className="min-w-0">
                <div className="whitespace-pre-wrap break-words">{n.texto}</div>
                <div className="text-xs text-muted-foreground">{data(n.created_at)}</div>
              </div>
              <Button
                size="icon"
                variant="ghost"
                className="size-8 shrink-0"
                disabled={excluir.isPending}
                onClick={() => excluir.mutate(n.id)}
              >
                <Trash2 className="size-3.5 text-destructive" />
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="flex gap-2">
        <Input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Anotação de suporte…"
          onKeyDown={(e) => e.key === "Enter" && adicionar()}
        />
        <Button onClick={adicionar} disabled={!texto.trim() || criar.isPending}>
          {criar.isPending ? <Loader2 className="animate-spin" /> : <Plus className="size-4" />}
        </Button>
      </div>
    </section>
  )
}

function TimelineItem({ h }: { h: HistoricoPlano }) {
  const pago = h.plano_codigo !== "free"
  return (
    <li className="flex items-center justify-between rounded-lg border border-border/60 px-3 py-2 text-sm">
      <div>
        <span
          className={cn(
            "rounded px-1.5 py-0.5 text-xs font-medium",
            pago ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground",
          )}
        >
          {h.plano_codigo}
        </span>
        {h.motivo ? (
          <span className="ml-2 text-xs text-muted-foreground">
            {MOTIVO[h.motivo] ?? h.motivo}
          </span>
        ) : null}
      </div>
      <span className="text-xs text-muted-foreground">
        {data(h.inicio)} {h.fim ? `→ ${data(h.fim)}` : "→ atual"}
      </span>
    </li>
  )
}
