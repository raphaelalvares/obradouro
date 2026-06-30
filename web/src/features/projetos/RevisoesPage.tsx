import {
  Check,
  ChevronLeft,
  FileText,
  GitPullRequestArrow,
  Loader2,
  Paperclip,
  PencilLine,
  Trash2,
  X,
} from "lucide-react"
import { useRef, useState, type FormEvent } from "react"
import { Link, useParams } from "react-router-dom"
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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { AnexoImage } from "@/features/anexos/AnexoImage"
import { ApiError, api } from "@/lib/api"
import { cn } from "@/lib/utils"
import {
  arquivoRevisaoPath,
  useContador,
  useDecidirRevisao,
  useExcluirArquivoRevisao,
  useProjeto,
  useRevisoes,
  useSubirRevisao,
  useUploadArquivoRevisao,
  type ContadorRevisoes,
  type Revisao,
  type RevisaoArquivo,
  type StatusRevisao,
} from "@/features/projetos/projetosApi"

// ações que abrem o diálogo de motivo (escolher/aprovar não passam por aqui)
type MotivoAcao = "alteracao" | "recusar"

const STATUS: Record<StatusRevisao, { label: string; cls: string }> = {
  pendente: { label: "Aguardando decisão", cls: "border-amber-500/50 bg-amber-500/10 text-amber-600" },
  aprovado: { label: "Aprovado", cls: "border-primary/50 bg-primary/10 text-primary" },
  alteracao_pedida: { label: "Alteração pedida", cls: "border-blue-500/50 bg-blue-500/10 text-blue-600" },
  recusado: { label: "Recusado", cls: "border-destructive/50 bg-destructive/10 text-destructive" },
}

const horaFmt = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })

// opções de layout que o arquiteto pode anexar (Sem opção = arquivo comum; 1-de-3 cobre o caso típico)
const OPCOES_UPLOAD: (number | null)[] = [null, 1, 2, 3]

export function RevisoesPage() {
  const { projetoId = "" } = useParams()
  const projeto = useProjeto(projetoId)
  const revisoes = useRevisoes(projetoId)
  const contador = useContador(projetoId)

  const ehArquiteto = projeto.data?.meu_papel === "arquiteto"
  const ehCliente = projeto.data?.meu_papel === "cliente"
  const lista = revisoes.data ?? []
  const temPendente = lista.some((r) => r.status === "pendente")
  const [novaOpen, setNovaOpen] = useState(false)

  return (
    <div className="animate-fade-up">
      <Link
        to={`/projetos/${projetoId}`}
        className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronLeft className="size-4" />
        {projeto.data?.nome ?? "Projeto"}
      </Link>

      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Ciclo de revisões</div>
          <h1 className="font-word text-4xl leading-none">REVISÕES</h1>
        </div>
        {ehArquiteto && lista.length > 0 && (
          <Button disabled={temPendente} title={temPendente ? "Aguarde a decisão do cliente" : undefined} onClick={() => setNovaOpen(true)}>
            <GitPullRequestArrow />
            Nova
          </Button>
        )}
      </div>

      {contador.data?.controla && <ContadorBanner c={contador.data} />}

      {(projeto.isLoading || revisoes.isLoading) && <CenteredSpinner />}
      {revisoes.isError && (
        <ErrorState message="Não foi possível carregar as revisões." onRetry={() => void revisoes.refetch()} />
      )}

      {revisoes.isSuccess && lista.length === 0 && (
        <EmptyState
          icon={GitPullRequestArrow}
          title="Nenhuma revisão ainda"
          description={
            ehArquiteto
              ? "Suba a entrega base (R0). O cliente poderá aprovar, recusar ou pedir alteração."
              : "O arquiteto ainda não subiu a primeira entrega."
          }
          action={
            ehArquiteto ? (
              <Button onClick={() => setNovaOpen(true)}>
                <GitPullRequestArrow />
                Subir entrega (R0)
              </Button>
            ) : undefined
          }
        />
      )}

      {lista.length > 0 && (
        <ul className="space-y-4">
          {/* mais recente primeiro */}
          {[...lista].reverse().map((r) => (
            <li key={r.id}>
              <RevisaoCard projetoId={projetoId} revisao={r} ehArquiteto={ehArquiteto} ehCliente={ehCliente} />
            </li>
          ))}
        </ul>
      )}

      <NovaRevisaoDialog
        projetoId={projetoId}
        open={novaOpen}
        onOpenChange={setNovaOpen}
        primeira={lista.length === 0}
      />
    </div>
  )
}

/** Contador visível a arquiteto E cliente (o sistema sinaliza, sem travar nem cobrar). */
function ContadorBanner({ c }: { c: ContadorRevisoes }) {
  const alem = c.alem_count > 0
  return (
    <div
      className={cn(
        "mb-5 flex items-center justify-between rounded-2xl border p-4",
        alem ? "border-amber-500/50 bg-amber-500/10" : "border-border bg-card",
      )}
    >
      <div>
        <div className="text-sm font-medium">
          {c.usadas} de {c.incluidas} alterações usadas
        </div>
        <div className="text-xs text-muted-foreground">
          {alem
            ? `${c.alem_count} ${c.alem_count === 1 ? "revisão" : "revisões"} além do incluído no contrato`
            : `${c.restantes} ${c.restantes === 1 ? "alteração restante" : "alterações restantes"}`}
        </div>
      </div>
      {alem && (
        <span className="rounded-full border border-amber-500/50 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wide text-amber-600">
          Além do incluído
        </span>
      )}
    </div>
  )
}

function RevisaoCard({
  projetoId,
  revisao,
  ehArquiteto,
  ehCliente,
}: {
  projetoId: string
  revisao: Revisao
  ehArquiteto: boolean
  ehCliente: boolean
}) {
  const st = STATUS[revisao.status]
  const upload = useUploadArquivoRevisao(projetoId, revisao.id)
  const excluirArq = useExcluirArquivoRevisao(projetoId, revisao.id)
  const decidirMut = useDecidirRevisao(projetoId)
  const fileRef = useRef<HTMLInputElement>(null)
  const [lightbox, setLightbox] = useState<RevisaoArquivo | null>(null)
  const [pendingDelete, setPendingDelete] = useState<RevisaoArquivo | null>(null)
  const [decisao, setDecisao] = useState<MotivoAcao | null>(null)
  // opção em que os próximos arquivos serão anexados (1-de-N de layout); null = arquivo comum
  const [uploadOpcao, setUploadOpcao] = useState<number | null>(null)
  const [escolhendo, setEscolhendo] = useState<number | null>(null)  // opção em escolha (spinner)

  // revisão "de opções" = tem arquivos com opcao não-nula → o cliente ESCOLHE uma (em vez de aprovar)
  const opcoesPresentes = [
    ...new Set(revisao.arquivos.filter((a) => a.opcao != null).map((a) => a.opcao as number)),
  ].sort((a, b) => a - b)
  const temOpcoes = opcoesPresentes.length > 0
  const semOpcao = revisao.arquivos.filter((a) => a.opcao == null)
  const pendente = revisao.status === "pendente"

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ""
    for (const f of files) {
      try {
        await upload.mutateAsync({ file: f, opcao: uploadOpcao })
      } catch (err) {
        if (err instanceof ApiError && err.isUpgrade) {
          toast.error(err.problem?.detail ?? "Armazenamento do plano esgotado.")
          break
        } else if (err instanceof ApiError && err.status === 415) {
          toast.error(`"${f.name}" deve ser imagem ou PDF.`)
        } else if (err instanceof ApiError && err.status === 413) {
          toast.error(`"${f.name}" é grande demais.`)
        } else {
          toast.error(`Não consegui enviar "${f.name}".`)
        }
      }
    }
  }

  async function onEscolher(opcao: number) {
    if (decidirMut.isPending) return
    setEscolhendo(opcao)
    try {
      await decidirMut.mutateAsync({ revisaoId: revisao.id, acao: "escolher", opcaoEscolhida: opcao })
      toast.success(`Opção ${opcao} escolhida`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível escolher a opção.")
    } finally {
      setEscolhendo(null)
    }
  }

  const renderTile = (a: RevisaoArquivo) => (
    <ArquivoTile
      key={a.id}
      projetoId={projetoId}
      revisaoId={revisao.id}
      arquivo={a}
      ehArquiteto={ehArquiteto}
      onAbrir={() => (a.is_pdf ? void abrirPdf(projetoId, revisao.id, a) : setLightbox(a))}
      onExcluir={() => setPendingDelete(a)}
    />
  )

  async function onConfirmDelete() {
    if (!pendingDelete) return
    try {
      await excluirArq.mutateAsync(pendingDelete.id)
      if (lightbox?.id === pendingDelete.id) setLightbox(null)
      setPendingDelete(null)
      toast.success("Arquivo removido")
    } catch {
      toast.error("Não foi possível remover.")
    }
  }

  return (
    <div className={cn("rounded-2xl border bg-card p-4", revisao.alem_do_incluido && "border-amber-500/40")}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-display text-lg">R{revisao.numero}</span>
            {revisao.titulo && <span className="min-w-0 break-words text-sm text-muted-foreground">{revisao.titulo}</span>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide", st.cls)}>
              {st.label}
            </span>
            {revisao.alem_do_incluido && (
              <span className="rounded-full border border-amber-500/50 px-2 py-0.5 text-[10px] uppercase tracking-wide text-amber-600">
                Além do incluído
              </span>
            )}
          </div>
        </div>
        <span className="shrink-0 text-xs text-muted-foreground">{horaFmt.format(new Date(revisao.created_at))}</span>
      </div>

      {/* anexar (arquiteto): escolhe em qual opção de layout o arquivo entra (Sem opção = comum) */}
      {ehArquiteto && (
        <div className="mb-3 space-y-2 rounded-xl border border-dashed border-border p-2.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Anexar como:</span>
            {OPCOES_UPLOAD.map((op) => (
              <button
                key={op ?? "sem"}
                type="button"
                onClick={() => setUploadOpcao(op)}
                className={cn(
                  "rounded-md border px-2 py-0.5 text-xs transition-colors",
                  uploadOpcao === op
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:text-foreground",
                )}
              >
                {op == null ? "Sem opção" : `Opção ${op}`}
              </button>
            ))}
          </div>
          <Button
            variant="outline"
            size="sm"
            disabled={upload.isPending}
            onClick={() => fileRef.current?.click()}
          >
            {upload.isPending ? <Loader2 className="animate-spin" /> : <Paperclip />}
            {uploadOpcao == null ? "Adicionar arquivo" : `Adicionar à opção ${uploadOpcao}`}
          </Button>
        </div>
      )}

      {/* arquivos: agrupados por opção (layouts 1-de-N) ou grade simples */}
      {temOpcoes ? (
        <div className="space-y-3">
          {opcoesPresentes.map((op) => {
            const arqs = revisao.arquivos.filter((a) => a.opcao === op)
            const escolhida = revisao.opcao_escolhida === op
            return (
              <div
                key={op}
                className={cn(
                  "rounded-xl border p-2.5",
                  escolhida ? "border-primary bg-primary/5" : "border-border",
                )}
              >
                <div className="mb-2 flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">Opção {op}</span>
                  {escolhida ? (
                    <span className="inline-flex items-center gap-1 rounded-full border border-primary/50 bg-primary/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-primary">
                      <Check className="size-3" />
                      Escolhida
                    </span>
                  ) : (
                    ehCliente &&
                    pendente && (
                      <Button size="sm" disabled={decidirMut.isPending} onClick={() => onEscolher(op)}>
                        {escolhendo === op ? <Loader2 className="animate-spin" /> : <Check />}
                        Escolher esta
                      </Button>
                    )
                  )}
                </div>
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">{arqs.map(renderTile)}</div>
              </div>
            )
          })}
          {semOpcao.length > 0 && (
            <div>
              <div className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
                Outros arquivos
              </div>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">{semOpcao.map(renderTile)}</div>
            </div>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {revisao.arquivos.map(renderTile)}
          {revisao.arquivos.length === 0 && (
            <p className="col-span-full py-2 text-xs text-muted-foreground">
              {ehArquiteto ? "Anexe os arquivos desta entrega." : "Sem arquivos nesta revisão."}
            </p>
          )}
        </div>
      )}

      {/* decisão tomada */}
      {revisao.status !== "pendente" && revisao.decidido_em && (
        <div className="mt-3 rounded-xl bg-accent/40 p-3 text-sm">
          <span className="text-muted-foreground">
            {revisao.decidido_por_nome ? `${revisao.decidido_por_nome} · ` : ""}
            {horaFmt.format(new Date(revisao.decidido_em))}
          </span>
          {revisao.motivo && <p className="mt-1 whitespace-pre-wrap">{revisao.motivo}</p>}
        </div>
      )}

      {/* verbos do cliente (só quando pendente). Com opções, aprovar = "Escolher esta" (por opção
          acima); aqui ficam só pedir alteração / recusar. */}
      {ehCliente && pendente && (
        <>
          {temOpcoes && (
            <p className="mt-3 text-xs text-muted-foreground">
              Escolha uma das opções acima para aprovar, ou peça alteração/recuse.
            </p>
          )}
          <div className={cn("mt-3 grid gap-2", temOpcoes ? "grid-cols-2" : "grid-cols-3")}>
            {!temOpcoes && <DecidirAprovar projetoId={projetoId} revisaoId={revisao.id} />}
            <Button variant="outline" size="sm" onClick={() => setDecisao("alteracao")}>
              <PencilLine />
              Alteração
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="text-destructive hover:bg-destructive/10 hover:text-destructive"
              onClick={() => setDecisao("recusar")}
            >
              <X />
              Recusar
            </Button>
          </div>
        </>
      )}

      <input ref={fileRef} type="file" accept="image/*,application/pdf" multiple className="hidden" onChange={onPick} />

      {/* Lightbox de imagem */}
      <Dialog open={lightbox !== null} onOpenChange={(o) => !o && setLightbox(null)}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle className="truncate text-lg">{lightbox?.nome_arquivo}</DialogTitle>
          </DialogHeader>
          {lightbox && (
            <AnexoImage
              path={arquivoRevisaoPath(projetoId, revisao.id, lightbox.id, "full")}
              alt={lightbox.nome_arquivo}
              fit="contain"
              className="max-h-[70vh] w-full rounded-xl bg-black/30"
            />
          )}
        </DialogContent>
      </Dialog>

      <DecisaoMotivoDialog
        projetoId={projetoId}
        revisaoId={revisao.id}
        acao={decisao}
        onOpenChange={(o) => !o && setDecisao(null)}
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title="Remover arquivo?"
        description={pendingDelete ? `"${pendingDelete.nome_arquivo}" será removido.` : undefined}
        pending={excluirArq.isPending}
        onConfirm={onConfirmDelete}
      />
    </div>
  )
}

function ArquivoTile({
  projetoId,
  revisaoId,
  arquivo,
  ehArquiteto,
  onAbrir,
  onExcluir,
}: {
  projetoId: string
  revisaoId: string
  arquivo: RevisaoArquivo
  ehArquiteto: boolean
  onAbrir: () => void
  onExcluir: () => void
}) {
  return (
    <div className="group relative aspect-square overflow-hidden rounded-xl border border-border">
      <button type="button" onClick={onAbrir} className="size-full" title={arquivo.nome_arquivo}>
        {arquivo.is_pdf ? (
          <span className="flex size-full flex-col items-center justify-center gap-1 bg-accent/40 text-muted-foreground">
            <FileText className="size-6" />
            <span className="px-1 text-[10px]">PDF</span>
          </span>
        ) : (
          <AnexoImage
            path={arquivoRevisaoPath(projetoId, revisaoId, arquivo.id, "thumb")}
            alt={arquivo.nome_arquivo}
            className="size-full"
          />
        )}
      </button>
      {ehArquiteto && (
        <button
          type="button"
          onClick={onExcluir}
          aria-label="Remover arquivo"
          className="absolute right-1 top-1 rounded-lg bg-black/55 p-1.5 text-white/90 opacity-0 transition-opacity hover:bg-destructive group-hover:opacity-100"
        >
          <Trash2 className="size-3.5" />
        </button>
      )}
    </div>
  )
}

function DecidirAprovar({ projetoId, revisaoId }: { projetoId: string; revisaoId: string }) {
  const decidir = useDecidirRevisao(projetoId)
  async function onAprovar() {
    if (decidir.isPending) return
    try {
      await decidir.mutateAsync({ revisaoId, acao: "aprovar" })
      toast.success("Revisão aprovada")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível aprovar.")
    }
  }
  return (
    <Button size="sm" disabled={decidir.isPending} onClick={onAprovar}>
      {decidir.isPending ? <Loader2 className="animate-spin" /> : <Check />}
      Aprovar
    </Button>
  )
}

function DecisaoMotivoDialog({
  projetoId,
  revisaoId,
  acao,
  onOpenChange,
}: {
  projetoId: string
  revisaoId: string
  acao: MotivoAcao | null
  onOpenChange: (open: boolean) => void
}) {
  const [motivo, setMotivo] = useState("")
  const decidir = useDecidirRevisao(projetoId)
  const open = acao === "alteracao" || acao === "recusar"
  const recusar = acao === "recusar"
  const valido = motivo.trim().length > 0

  function close(o: boolean) {
    if (!o) setMotivo("")
    onOpenChange(o)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || !acao || decidir.isPending) return
    try {
      await decidir.mutateAsync({ revisaoId, acao, motivo })
      toast.success(recusar ? "Revisão recusada" : "Alteração solicitada")
      close(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível enviar.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{recusar ? "Recusar revisão" : "Pedir alteração"}</DialogTitle>
          <DialogDescription>
            {recusar
              ? "Diga ao arquiteto o motivo da recusa."
              : "Descreva o que precisa ser alterado nesta entrega."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="motivo">Motivo</Label>
            <Textarea
              id="motivo"
              required
              value={motivo}
              maxLength={2000}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder={recusar ? "Ex.: não atende ao briefing…" : "Ex.: trocar a cor da bancada…"}
            />
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => close(false)}>
              Cancelar
            </Button>
            <Button
              type="submit"
              variant={recusar ? "destructive" : "default"}
              className="flex-1"
              disabled={!valido || decidir.isPending}
            >
              {decidir.isPending && <Loader2 className="animate-spin" />}
              {recusar ? "Recusar" : "Pedir alteração"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function NovaRevisaoDialog({
  projetoId,
  open,
  onOpenChange,
  primeira,
}: {
  projetoId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  primeira: boolean
}) {
  const [titulo, setTitulo] = useState("")
  const subir = useSubirRevisao(projetoId)

  function close(o: boolean) {
    if (!o) setTitulo("")
    onOpenChange(o)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (subir.isPending) return
    try {
      const r = await subir.mutateAsync({ titulo: titulo.trim() || null })
      toast.success(`R${r.numero} criada — anexe os arquivos`)
      close(false)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast.error("Já existe uma revisão aguardando decisão do cliente.")
      } else {
        toast.error(err instanceof ApiError ? err.message : "Não foi possível criar a revisão.")
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{primeira ? "Entrega base (R0)" : "Nova revisão"}</DialogTitle>
          <DialogDescription>
            {primeira
              ? "A primeira entrega para o cliente avaliar."
              : "Uma nova versão após o pedido de alteração."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="titulo-rev">Título (opcional)</Label>
            <Input
              id="titulo-rev"
              maxLength={200}
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Ex.: Planta baixa + 3D"
            />
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => close(false)}>
              Cancelar
            </Button>
            <Button type="submit" className="flex-1" disabled={subir.isPending}>
              {subir.isPending && <Loader2 className="animate-spin" />}
              Criar revisão
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Abre um PDF de revisão em nova aba (fetch autenticado → blob URL). */
async function abrirPdf(projetoId: string, revisaoId: string, arquivo: RevisaoArquivo) {
  try {
    const blob = await api.getBlob(arquivoRevisaoPath(projetoId, revisaoId, arquivo.id, "full"))
    const url = URL.createObjectURL(blob)
    window.open(url, "_blank", "noopener,noreferrer")
    // revoga depois de um tempo (deixa a aba carregar)
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch {
    toast.error("Não foi possível abrir o PDF.")
  }
}
