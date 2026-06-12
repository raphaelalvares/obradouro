import { Check, FileDown, FileText, Loader2, MessageSquare, Send, X } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { ApiError } from "@/lib/api"
import { formatBRL } from "@/features/comercial/format"
import {
  baixarPropostaPdf,
  useDecidirProposta,
  useProposta,
  usePropostas,
  type DecisaoAcao,
} from "@/features/orcamento/orcamentosApi"

const dataFmt = (iso: string | null) => {
  if (!iso) return "—"
  const [y, m, d] = iso.split("-")
  return `${d}/${m}/${y.slice(2)}`
}

const DECISAO_INFO: Record<DecisaoAcao, { label: string; cls: string }> = {
  aprovado: { label: "Aprovada", cls: "border-primary/50 bg-primary/10 text-primary" },
  alteracao_pedida: {
    label: "Alteração pedida",
    cls: "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400",
  },
  recusado: { label: "Recusada", cls: "border-destructive/50 bg-destructive/10 text-destructive" },
}

/**
 * Visão de PROPOSTA do orçamento (portal do CLIENTE): versões ENVIADAS, com preços de VENDA por
 * linha — sem custos internos nem percentuais. Também serve de "como o cliente vê" p/ o arquiteto.
 */
export function PropostaView({ projetoId }: { projetoId: string }) {
  const propostas = usePropostas(projetoId)
  const [selId, setSelId] = useState<string | null>(null)
  const [baixando, setBaixando] = useState(false)

  // seleciona a proposta mais recente por padrão; mantém a escolha se ainda existir
  useEffect(() => {
    const lista = propostas.data
    if (!lista || lista.length === 0) return
    const alvo = lista[lista.length - 1].id
    setSelId((prev) => (prev && lista.some((p) => p.id === prev) ? prev : alvo))
  }, [propostas.data])

  const proposta = useProposta(projetoId, selId)
  const p = proposta.data
  const decidir = useDecidirProposta(projetoId)
  const [confirmAprovar, setConfirmAprovar] = useState(false)
  // dialog de motivo p/ recusar / pedir alteração
  const [motivoDe, setMotivoDe] = useState<"alteracao_pedida" | "recusado" | null>(null)
  const [motivo, setMotivo] = useState("")

  async function enviarDecisao(acao: DecisaoAcao, txtMotivo?: string) {
    if (!selId) return
    try {
      await decidir.mutateAsync({ versaoId: selId, acao, motivo: txtMotivo ?? null })
      toast.success(
        acao === "aprovado"
          ? "Proposta aprovada — o arquiteto foi avisado."
          : acao === "recusado"
            ? "Proposta recusada — o arquiteto foi avisado."
            : "Pedido de alteração enviado ao arquiteto.",
      )
      setConfirmAprovar(false)
      setMotivoDe(null)
      setMotivo("")
    } catch (err) {
      // a versão pode ter sido superada por uma nova revisão (ou já decidida) no servidor →
      // recarrega a lista p/ a versão obsoleta sair do portal e o cliente ver a vigente.
      void propostas.refetch()
      toast.error(err instanceof ApiError ? err.message : "Não foi possível registrar a decisão.")
    }
  }

  async function baixarPdf() {
    if (baixando || !selId || !p) return
    setBaixando(true)
    try {
      await baixarPropostaPdf(projetoId, selId, p.numero)
    } catch (err) {
      if (err instanceof ApiError && err.isUpgrade) {
        toast.error("A proposta em PDF é um recurso Pro.", {
          description: "O plano do escritório não inclui exportação em PDF.",
        })
      } else {
        toast.error("Não foi possível gerar o PDF.")
      }
    } finally {
      setBaixando(false)
    }
  }

  if (propostas.isLoading) return <CenteredSpinner />
  if (propostas.isError) {
    return (
      <ErrorState
        message="Não foi possível carregar a proposta."
        onRetry={() => void propostas.refetch()}
      />
    )
  }
  if ((propostas.data?.length ?? 0) === 0) {
    return (
      <EmptyState
        icon={FileText}
        title="Nenhuma proposta ainda"
        description="Quando o arquiteto enviar a proposta do orçamento, ela aparece aqui."
      />
    )
  }

  return (
    <>
      {propostas.data!.length > 1 && (
        <div className="-mx-5 mb-4 flex gap-1.5 overflow-x-auto px-5 pb-1">
          {propostas.data!.map((rv) => {
            const ativo = rv.id === selId
            return (
              <button
                key={rv.id}
                type="button"
                aria-pressed={ativo}
                onClick={() => setSelId(rv.id)}
                className={cn(
                  "inline-flex shrink-0 items-center gap-1.5 rounded-xl border px-3 py-1.5 text-left text-xs transition-colors",
                  ativo ? "border-primary bg-primary/10" : "border-border hover:border-primary/40",
                )}
              >
                <span className="font-display font-semibold">R{rv.numero}</span>
                <span className="text-muted-foreground">{formatBRL(rv.preco_final)}</span>
              </button>
            )
          })}
        </div>
      )}

      {proposta.isLoading && <CenteredSpinner />}

      {proposta.isError && (
        <ErrorState
          message="Não foi possível carregar a proposta."
          onRetry={() => void proposta.refetch()}
        />
      )}

      {p && (
        <>
          {/* cabeçalho da proposta */}
          <div className="mb-4 rounded-2xl border border-primary/50 bg-card p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="inline-flex items-center gap-1.5 text-xs text-primary">
                  <Send className="size-3.5" />
                  Proposta R{p.numero}
                </div>
                <div className="mt-1 font-display text-3xl leading-none tabular-nums">
                  {formatBRL(p.preco_final)}
                </div>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span>Data: <span className="text-foreground">{dataFmt(p.data)}</span></span>
                  <span>
                    Válida até: <span className="text-foreground">{dataFmt(p.validade)}</span>
                  </span>
                </div>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-2">
                {p.decisao && (
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium",
                      DECISAO_INFO[p.decisao].cls,
                    )}
                  >
                    {DECISAO_INFO[p.decisao].label}
                    {p.decidido_em ? ` · ${dataFmt(p.decidido_em.slice(0, 10))}` : ""}
                  </span>
                )}
                <Button variant="outline" size="sm" disabled={baixando} onClick={() => void baixarPdf()}>
                  {baixando ? <Loader2 className="animate-spin" /> : <FileDown />}
                  Baixar PDF
                </Button>
              </div>
            </div>

            {/* decisão do cliente: pendente → ações; decidida → motivo (se houver) */}
            {p.decisao == null ? (
              <div className="mt-4 flex flex-wrap gap-2 border-t border-border pt-4">
                <Button
                  size="sm"
                  className="flex-1"
                  disabled={decidir.isPending}
                  onClick={() => setConfirmAprovar(true)}
                >
                  {decidir.isPending ? <Loader2 className="animate-spin" /> : <Check />}
                  Aprovar
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={decidir.isPending}
                  onClick={() => {
                    setMotivo("")
                    setMotivoDe("alteracao_pedida")
                  }}
                >
                  <MessageSquare />
                  Pedir alteração
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                  disabled={decidir.isPending}
                  onClick={() => {
                    setMotivo("")
                    setMotivoDe("recusado")
                  }}
                >
                  <X />
                  Recusar
                </Button>
              </div>
            ) : (
              p.decisao_motivo && (
                <div className="mt-4 border-t border-border pt-3 text-sm">
                  <span className="text-muted-foreground">Seu comentário: </span>
                  <span className="whitespace-pre-wrap break-words">{p.decisao_motivo}</span>
                </div>
              )
            )}
          </div>

          {/* etapas → linhas com preço de venda */}
          <div className="space-y-4">
            {p.etapas.map((g) => (
              <div key={g.etapa} className="rounded-2xl border border-border bg-card">
                <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2">
                  <span className="break-words text-sm font-semibold uppercase tracking-wide">
                    {g.etapa}
                  </span>
                  <span className="shrink-0 font-display text-sm tabular-nums text-muted-foreground">
                    {formatBRL(g.valor)}
                  </span>
                </div>
                <ul className="divide-y divide-border">
                  {g.itens.map((it, i) => (
                    <li key={i} className="flex items-start gap-2 px-4 py-2.5">
                      <div className="min-w-0 flex-1">
                        <p className="break-words text-sm font-medium">{it.descricao}</p>
                        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                          {it.ambiente && (
                            <span className="rounded bg-accent px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
                              {it.ambiente}
                            </span>
                          )}
                          {(it.quantidade != null || it.unidade) && (
                            <span>
                              {it.quantidade != null
                                ? String(it.quantidade).replace(".", ",")
                                : ""}
                              {it.unidade ? ` ${it.unidade}` : ""}
                            </span>
                          )}
                        </div>
                      </div>
                      <span className="shrink-0 font-display text-sm tabular-nums">
                        {formatBRL(it.valor)}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          {p.observacoes && (
            <div className="mt-4 rounded-2xl border border-border bg-card p-4">
              <div className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
                Condições e observações
              </div>
              <p className="whitespace-pre-wrap break-words text-sm">{p.observacoes}</p>
            </div>
          )}
        </>
      )}

      <ConfirmDialog
        open={confirmAprovar}
        onOpenChange={setConfirmAprovar}
        title="Aprovar proposta"
        description={
          p ? `Confirmar a aprovação da proposta R${p.numero} (${formatBRL(p.preco_final)})? O arquiteto será avisado.` : ""
        }
        confirmLabel="Aprovar"
        variant="default"
        pending={decidir.isPending}
        onConfirm={() => void enviarDecisao("aprovado")}
      />

      <Dialog open={motivoDe !== null} onOpenChange={(o) => !o && setMotivoDe(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {motivoDe === "recusado" ? "Recusar proposta" : "Pedir alteração"}
            </DialogTitle>
            <DialogDescription>
              {motivoDe === "recusado"
                ? "Conte ao arquiteto o motivo da recusa."
                : "Descreva o que você gostaria de ajustar na proposta."}
            </DialogDescription>
          </DialogHeader>
          <Textarea
            aria-label="Motivo"
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Escreva aqui…"
            rows={4}
            maxLength={2000}
          />
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              className="flex-1"
              onClick={() => setMotivoDe(null)}
            >
              Cancelar
            </Button>
            <Button
              type="button"
              className="flex-1"
              disabled={decidir.isPending || motivo.trim().length === 0}
              onClick={() => motivoDe && void enviarDecisao(motivoDe, motivo.trim())}
            >
              {decidir.isPending && <Loader2 className="animate-spin" />}
              {motivoDe === "recusado" ? "Recusar" : "Enviar pedido"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
