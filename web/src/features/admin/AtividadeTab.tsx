import { Card } from "@/components/ui/card"
import { CenteredSpinner, ErrorState } from "@/components/feedback/states"

import { useAuditLog, type AuditLog } from "./adminApi"

const fmt = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
})

// acao crua → rótulo amigável.
const ACAO: Record<string, string> = {
  acesso_autorizado: "convidou cliente",
  acesso_revogado: "revogou cliente",
  reenviar_confirmacao: "reenviou confirmação",
  reset_senha: "gerou link de reset",
  suspender: "suspendeu conta",
  reativar: "reativou conta",
}

export function AtividadeTab() {
  const log = useAuditLog()

  if (log.isLoading) return <CenteredSpinner />
  if (log.isError)
    return <ErrorState message="Não foi possível carregar a atividade." onRetry={() => log.refetch()} />

  const itens = log.data ?? []
  if (itens.length === 0)
    return <p className="py-10 text-center text-muted-foreground">Nenhuma ação registrada ainda.</p>

  return (
    <Card className="divide-y divide-border/60">
      {itens.map((l) => (
        <Linha key={l.id} l={l} />
      ))}
    </Card>
  )
}

function Linha({ l }: { l: AuditLog }) {
  return (
    <div className="flex items-start justify-between gap-3 px-4 py-3 text-sm">
      <div className="min-w-0">
        <div>
          <span className="font-medium">{ACAO[l.acao] ?? l.acao}</span>
          {l.tenant_email && <span className="text-muted-foreground"> · {l.tenant_email}</span>}
        </div>
        <div className="text-xs text-muted-foreground">
          {l.admin_email ?? "admin"}
          {(() => {
            const d = l.detalhe as { email?: string }
            return d?.email ? ` · ${d.email}` : ""
          })()}
        </div>
      </div>
      <div className="shrink-0 text-xs text-muted-foreground">{fmt.format(new Date(l.created_at))}</div>
    </div>
  )
}
