import {
  Check,
  CreditCard,
  Crown,
  Download,
  FileArchive,
  ImageIcon,
  Loader2,
  Lock,
  RotateCcw,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { toast } from "sonner"

import { AnexoImage } from "@/features/anexos/AnexoImage"
import { CenteredSpinner, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError } from "@/lib/api"
import {
  LOGO_PATH,
  useBranding,
  useQuota,
  useRemoverLogo,
  useSalvarBranding,
  useUploadLogo,
} from "@/features/conta/contaApi"
import {
  useAssinar,
  useCancelarAssinatura,
  useCobranca,
  useInvalidarCobranca,
  usePlanosAssinaveis,
  usePortal,
  useReativarAssinatura,
} from "@/features/conta/cobrancaApi"
import { brlCentavos } from "@/lib/num"
import {
  baixarExport,
  useExports,
  useSolicitarExport,
  type ExportJob,
} from "@/features/conta/exportApi"
import { abrirPaywall } from "@/features/planos/paywall"
import { planoLabel } from "@/features/planos/planos"
import { cn } from "@/lib/utils"

// Régua comercial (o texto de venda; os limites REAIS moram no catálogo public.planos). Mantém a
// ordem free → alicerce → mestre p/ o comparativo destacar o "seu plano" e os superiores.
const REGUA = [
  {
    codigo: "free",
    nome: "Canteiro",
    preco: "R$ 0",
    periodo: "para sempre",
    tagline: "Teste com 1 obra de verdade",
    itens: [
      "1 obra ativa",
      "500 MB de fotos",
      "Proposta em PDF (com marca d'água)",
      "EAP, cronograma, diário, estoque e comercial",
    ],
  },
  {
    codigo: "alicerce",
    nome: "Alicerce",
    preco: "R$ 59",
    periodo: "/mês",
    tagline: "Para o fluxo constante do escritório",
    itens: [
      "5 obras ativas",
      "5 GB de fotos",
      "Proposta sem marca d'água + seu logo",
      "Exporta cronograma e checklist (PDF/Excel)",
    ],
  },
  {
    codigo: "pro",
    nome: "Mestre",
    preco: "R$ 179",
    periodo: "/mês",
    tagline: "Muitas obras e portal do cliente",
    itens: [
      "Obras ilimitadas",
      "50 GB de fotos",
      "Portal do cliente (3D + manual)",
      "Assistente com IA",
    ],
  },
]

const dataFmt = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" })
function fmtData(iso: string | null) {
  return iso ? dataFmt.format(new Date(iso)) : ""
}

function fmtMb(bytes: number) {
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
function fmtLimite(n: number, unidade: string) {
  return n < 0 ? "ilimitado" : `${n} ${unidade}`
}

export function ConfiguracoesPage() {
  const branding = useBranding()

  return (
    <div className="animate-fade-up space-y-6">
      <div>
        <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Conta</div>
        <h1 className="font-word text-4xl leading-none">CONFIGURAÇÕES</h1>
      </div>

      {/* ---------------- plano + assinatura ---------------- */}
      <PlanoCard />

      {/* ---------------- personalização (logo) ---------------- */}
      {branding.isLoading ? (
        <CenteredSpinner />
      ) : branding.isError || !branding.data ? (
        <ErrorState
          message="Não foi possível carregar a personalização."
          onRetry={() => void branding.refetch()}
        />
      ) : (
        <PersonalizacaoCard
          podePersonalizar={branding.data.pode_personalizar}
          temLogo={branding.data.tem_logo}
          nomeAtual={branding.data.nome_escritorio}
        />
      )}

      {/* ---------------- exportar dados (LGPD) ---------------- */}
      <ExportCard />
    </div>
  )
}

function PlanoCard() {
  const quota = useQuota()
  const cobranca = useCobranca()
  const planos = usePlanosAssinaveis()
  const assinar = useAssinar()
  const portal = usePortal()
  const cancelar = useCancelarAssinatura()
  const reativar = useReativarAssinatura()
  const invalidar = useInvalidarCobranca()
  const [confirmarCancel, setConfirmarCancel] = useState(false)
  const [params, setParams] = useSearchParams()

  // retorno do Stripe Checkout (?cobranca=sucesso|cancelado) → avisa + atualiza + limpa a URL
  useEffect(() => {
    const r = params.get("cobranca")
    if (!r) return
    if (r === "sucesso") {
      toast.success("Assinatura concluída!", { description: "Seu plano será atualizado em instantes." })
      invalidar()
    } else if (r === "cancelado") {
      toast("Checkout cancelado.")
    }
    params.delete("cobranca")
    setParams(params, { replace: true })
  }, [params, setParams, invalidar])

  if (quota.isLoading) return <CenteredSpinner />
  if (quota.isError || !quota.data)
    return <ErrorState message="Não foi possível carregar o plano." onRetry={() => void quota.refetch()} />

  const c = cobranca.data
  const planoAtual = quota.data.plano
  const ePago = planoAtual !== "free"
  const podeGerenciar = Boolean(c?.tem_assinatura || c?.status)
  const agendado = Boolean(c?.cancelamento_agendado)
  // planos que dá pra contratar agora (≠ do atual). Sem Stripe configurado a lista vem vazia.
  const assinaveis = (planos.data ?? []).filter((p) => p.codigo !== planoAtual)
  const armaz = quota.data.armazenamento
  const pctArmaz =
    armaz.limite_mb > 0 ? armaz.usado_bytes / (armaz.limite_mb * 1024 * 1024) : 0

  async function onCancelar() {
    try {
      await cancelar.mutateAsync()
      setConfirmarCancel(false)
      toast.success("Cancelamento agendado", {
        description: "Você mantém o acesso até o fim do período já pago.",
      })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível cancelar.")
    }
  }

  async function onReativar() {
    try {
      await reativar.mutateAsync()
      toast.success("Assinatura reativada", { description: "Volta a renovar normalmente." })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível reativar.")
    }
  }

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-wider text-muted-foreground">Plano atual</div>
          <div className="mt-0.5 flex items-center gap-2">
            <Crown className={ePago ? "size-4 text-primary" : "size-4 text-muted-foreground"} />
            <span className="text-lg font-medium">{planoLabel(planoAtual)}</span>
            {c?.status === "past_due" && (
              <span className="rounded-full border border-amber-500/50 px-2 py-0.5 text-[10px] uppercase text-amber-600">
                pagamento pendente
              </span>
            )}
          </div>
          {c?.tem_assinatura && c.current_period_end && (
            <p className="mt-1 text-xs text-muted-foreground">
              {c.cancelamento_agendado || c.status === "canceled" ? "acesso até" : "renova em"}{" "}
              {fmtData(c.current_period_end)}
            </p>
          )}
          {c?.assinante_desde && (
            <p className="text-xs text-muted-foreground">cliente desde {fmtData(c.assinante_desde)}</p>
          )}
          {c?.ultimo_pagamento_em && c.ultimo_pagamento_cents != null && (
            <p className="text-xs text-muted-foreground">
              último pagamento {brlCentavos(c.ultimo_pagamento_cents)} em{" "}
              {fmtData(c.ultimo_pagamento_em)}
            </p>
          )}
        </div>
        {c?.configurado && podeGerenciar && (
          <Button variant="outline" onClick={() => portal.mutate()} disabled={portal.isPending}>
            {portal.isPending ? <Loader2 className="animate-spin" /> : <CreditCard />}
            Gerenciar
          </Button>
        )}
      </div>

      {/* cancelamento agendado: avisa + permite reativar (mantém o acesso até o fim do período) */}
      {c?.configurado && agendado && (
        <div className="mt-4 flex flex-col gap-2 rounded-xl border border-amber-500/40 bg-amber-500/5 p-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-amber-700 dark:text-amber-500">
            Cancelamento agendado — você mantém o {planoAtual}
            {c.current_period_end ? ` até ${fmtData(c.current_period_end)}` : ""}.
          </p>
          <Button
            size="sm"
            variant="outline"
            className="shrink-0"
            onClick={onReativar}
            disabled={reativar.isPending}
          >
            {reativar.isPending ? <Loader2 className="animate-spin" /> : <RotateCcw />}
            Reativar
          </Button>
        </div>
      )}

      <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-xl border border-border p-3">
          <div className="text-xs text-muted-foreground">Obras ativas</div>
          <div className="mt-0.5 font-medium">
            {quota.data.obras_ativas.em_uso} / {fmtLimite(quota.data.obras_ativas.limite, "")}
          </div>
        </div>
        <div className="rounded-xl border border-border p-3">
          <div className="text-xs text-muted-foreground">Armazenamento</div>
          <div className="mt-0.5 font-medium">
            {fmtMb(quota.data.armazenamento.usado_bytes)} /{" "}
            {fmtLimite(quota.data.armazenamento.limite_mb, "MB")}
          </div>
        </div>
      </div>

      {/* armazenamento quase cheio → aviso + o comparativo abaixo é o CTA */}
      {pctArmaz >= 0.8 && (
        <div className="mt-4 rounded-xl border border-amber-500/40 bg-amber-500/5 p-3 text-sm text-amber-700 dark:text-amber-500">
          Seu armazenamento está em <strong>{Math.round(pctArmaz * 100)}%</strong>. Suba de plano
          para não parar de enviar fotos da obra.
        </div>
      )}

      {/* comparativo dos 3 planos (a "loja" interna). Sempre visível — vale como propaganda mesmo
          antes do Stripe estar configurado; o botão Assinar só aparece p/ planos assináveis. */}
      <PlanosComparativo
        planoAtual={planoAtual}
        assinaveis={assinaveis.map((p) => p.codigo)}
        configurado={Boolean(c?.configurado)}
        onAssinar={(cod) => assinar.mutate(cod)}
        assinandoCodigo={assinar.isPending ? (assinar.variables as string) : null}
      />

      {/* cancelar assinatura (no fim do período) — só quando há assinatura ativa e nada agendado */}
      {c?.configurado && c.tem_assinatura && !agendado && (
        <div className="mt-4 border-t border-border pt-3">
          <button
            type="button"
            onClick={() => setConfirmarCancel(true)}
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-destructive"
          >
            <XCircle className="size-3.5" />
            Cancelar assinatura
          </button>
        </div>
      )}

      <ConfirmDialog
        open={confirmarCancel}
        onOpenChange={setConfirmarCancel}
        title="Cancelar assinatura?"
        description={
          <>
            A cobrança não se repete. Você continua com o <strong>{planoAtual}</strong>
            {c?.current_period_end ? ` até ${fmtData(c.current_period_end)}` : " até o fim do período já pago"} e
            depois a conta volta para o plano grátis. Dá pra reativar antes disso.
          </>
        }
        confirmLabel="Cancelar assinatura"
        pending={cancelar.isPending}
        onConfirm={onCancelar}
      />
    </Card>
  )
}

// Comparativo dos 3 planos (usado dentro do PlanoCard). Destaca o plano atual e mostra o botão
// Assinar só nos planos superiores que já têm Stripe Price (assinaveis) — os demais mostram só o
// texto de venda (propaganda). O backend é a trava real; aqui é vitrine + CTA.
function PlanosComparativo({
  planoAtual,
  assinaveis,
  configurado,
  onAssinar,
  assinandoCodigo,
}: {
  planoAtual: string
  assinaveis: string[]
  configurado: boolean
  onAssinar: (codigo: string) => void
  assinandoCodigo: string | null
}) {
  const idxAtual = REGUA.findIndex((r) => r.codigo === planoAtual)
  return (
    <div className="mt-6 space-y-3">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">Planos</div>
      <div className="grid gap-3 sm:grid-cols-3">
        {REGUA.map((r, i) => {
          const atual = r.codigo === planoAtual
          const superior = i > idxAtual
          const podeAssinar = configurado && superior && assinaveis.includes(r.codigo)
          return (
            <div
              key={r.codigo}
              className={cn(
                "flex flex-col rounded-2xl border p-4",
                atual ? "border-primary bg-primary/5" : "border-border",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{r.nome}</span>
                {atual && (
                  <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[10px] uppercase tracking-wide text-primary">
                    seu plano
                  </span>
                )}
              </div>
              <div className="mt-1 flex items-baseline gap-1">
                <span className="text-2xl font-semibold">{r.preco}</span>
                <span className="text-xs text-muted-foreground">{r.periodo}</span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{r.tagline}</p>
              <ul className="mt-3 flex-1 space-y-1.5 text-sm">
                {r.itens.map((it) => (
                  <li key={it} className="flex gap-2">
                    <Check className="mt-0.5 size-3.5 shrink-0 text-primary" />
                    <span>{it}</span>
                  </li>
                ))}
              </ul>
              {!atual && superior && (
                <div className="mt-4">
                  {podeAssinar ? (
                    <Button
                      className="w-full"
                      onClick={() => onAssinar(r.codigo)}
                      disabled={assinandoCodigo != null}
                    >
                      {assinandoCodigo === r.codigo && <Loader2 className="animate-spin" />}
                      Assinar {r.nome}
                    </Button>
                  ) : (
                    <p className="text-center text-[11px] text-muted-foreground">
                      {configurado ? "Em breve" : "Assinatura em configuração"}
                    </p>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

const STATUS_EXPORT: Record<ExportJob["status"], string> = {
  pendente: "Na fila…",
  processando: "Gerando…",
  pronto: "Pronto",
  erro: "Falhou",
  expirado: "Expirado",
}

function ExportCard() {
  const exports = useExports()
  const solicitar = useSolicitarExport()
  const [baixando, setBaixando] = useState<string | null>(null)

  const lista = exports.data ?? []
  const rodando = lista.some((j) => j.status === "pendente" || j.status === "processando")

  async function onGerar() {
    try {
      await solicitar.mutateAsync()
      toast.success("Export solicitado", { description: "Avisaremos aqui quando o .zip ficar pronto." })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível solicitar o export.")
    }
  }

  async function onBaixar(id: string) {
    setBaixando(id)
    try {
      await baixarExport(id)
    } catch {
      toast.error("Não foi possível baixar o arquivo.")
    } finally {
      setBaixando(null)
    }
  }

  return (
    <Card className="space-y-4 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-medium">Exportar meus dados</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Gera um .zip com fotos por obra + planilhas (checklist e estoque). Fica disponível por 30
            dias.
          </p>
        </div>
        <Button onClick={onGerar} disabled={solicitar.isPending || rodando}>
          {solicitar.isPending || rodando ? <Loader2 className="animate-spin" /> : <FileArchive />}
          Gerar export
        </Button>
      </div>

      {exports.isLoading ? (
        <CenteredSpinner className="py-6" />
      ) : lista.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhum export ainda.</p>
      ) : (
        <ul className="divide-y divide-border overflow-hidden rounded-xl border border-border">
          {lista.map((j) => (
            <li key={j.id} className="flex items-center justify-between gap-3 bg-card p-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-sm">
                  {(j.status === "pendente" || j.status === "processando") && (
                    <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
                  )}
                  <span
                    className={
                      j.status === "pronto"
                        ? "text-primary"
                        : j.status === "erro"
                          ? "text-destructive"
                          : "text-muted-foreground"
                    }
                  >
                    {STATUS_EXPORT[j.status]}
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {fmtData(j.created_at)}
                  {j.status === "pronto" && j.expira_em ? ` · disponível até ${fmtData(j.expira_em)}` : ""}
                  {j.status === "expirado" ? " · arquivo expurgado" : ""}
                </div>
              </div>
              {j.status === "pronto" && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onBaixar(j.id)}
                  disabled={baixando === j.id}
                >
                  {baixando === j.id ? <Loader2 className="animate-spin" /> : <Download />}
                  Baixar
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function PersonalizacaoCard({
  podePersonalizar,
  temLogo,
  nomeAtual,
}: {
  podePersonalizar: boolean
  temLogo: boolean
  nomeAtual: string | null
}) {
  const salvar = useSalvarBranding()
  const upload = useUploadLogo()
  const remover = useRemoverLogo()
  const inputRef = useRef<HTMLInputElement>(null)
  const [nome, setNome] = useState(nomeAtual ?? "")

  useEffect(() => setNome(nomeAtual ?? ""), [nomeAtual])

  const nomeMudou = (nome.trim() || null) !== (nomeAtual ?? null)

  async function onSalvarNome() {
    try {
      await salvar.mutateAsync({ nome_escritorio: nome.trim() || null })
      toast.success("Personalização salva")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar.")
    }
  }

  async function onArquivo(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = "" // permite re-selecionar o mesmo arquivo
    if (!file) return
    try {
      await upload.mutateAsync(file)
      toast.success("Logo atualizado")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível enviar o logo.")
    }
  }

  async function onRemover() {
    try {
      await remover.mutateAsync()
      toast.success("Logo removido")
    } catch {
      toast.error("Não foi possível remover o logo.")
    }
  }

  if (!podePersonalizar) {
    return (
      <Card className="p-5">
        <div className="flex items-start gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-full bg-accent text-primary">
            <Lock className="size-5" />
          </div>
          <div>
            <h2 className="font-medium">Personalização do escritório</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Coloque o nome e o logo do seu escritório nos PDFs (e tire a marca d'água da proposta).
              Disponível a partir do <span className="text-primary">plano Alicerce</span>.
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => abrirPaywall({ eixo: "logo" })}
            >
              Ver planos
            </Button>
          </div>
        </div>
      </Card>
    )
  }

  return (
    <Card className="space-y-5 p-5">
      <div>
        <h2 className="font-medium">Personalização do escritório</h2>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Aparece no cabeçalho do PDF do checklist.
        </p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="nome-escritorio">Nome do escritório</Label>
        <div className="flex gap-2">
          <Input
            id="nome-escritorio"
            value={nome}
            maxLength={120}
            placeholder="Ex.: Estúdio Marina Arquitetura"
            onChange={(e) => setNome(e.target.value)}
          />
          <Button onClick={onSalvarNome} disabled={!nomeMudou || salvar.isPending}>
            {salvar.isPending && <Loader2 className="animate-spin" />}
            Salvar
          </Button>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label>Logo</Label>
        <div className="flex items-center gap-4">
          <div className="flex size-24 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border bg-muted/30">
            {temLogo ? (
              <AnexoImage path={LOGO_PATH} alt="Logo do escritório" fit="contain" className="size-full" />
            ) : (
              <ImageIcon className="size-7 text-muted-foreground" />
            )}
          </div>
          <div className="flex flex-col gap-2">
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={onArquivo}
            />
            <Button
              variant="outline"
              onClick={() => inputRef.current?.click()}
              disabled={upload.isPending}
            >
              {upload.isPending ? <Loader2 className="animate-spin" /> : <Upload />}
              {temLogo ? "Trocar logo" : "Enviar logo"}
            </Button>
            {temLogo && (
              <Button
                variant="ghost"
                className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                onClick={onRemover}
                disabled={remover.isPending}
              >
                {remover.isPending ? <Loader2 className="animate-spin" /> : <Trash2 />}
                Remover
              </Button>
            )}
            <p className="text-xs text-muted-foreground">PNG ou JPG. Fundo transparente fica melhor.</p>
          </div>
        </div>
      </div>
    </Card>
  )
}
