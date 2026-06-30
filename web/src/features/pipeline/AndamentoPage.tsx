import {
  ArrowRight,
  Check,
  ChevronLeft,
  ExternalLink,
  FileText,
  Link2,
  Loader2,
  Paperclip,
  Pencil,
  Trash2,
} from "lucide-react"
import { useRef, useState, type FormEvent } from "react"
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"

import { CenteredSpinner, ErrorState } from "@/components/feedback/states"
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
import { AnexoImage } from "@/features/anexos/AnexoImage"
import { ApiError, api } from "@/lib/api"
import { cn } from "@/lib/utils"
import {
  conteudoEtapaAnexoPath,
  useAdicionarEtapaLink,
  useAtualizarEtapa,
  useDecidirIniciarObra,
  useExcluirEtapaAnexo,
  usePipeline,
  useUploadEtapaArquivo,
  type EtapaAnexo,
  type EtapaProjeto,
  type StatusEtapa,
} from "@/features/pipeline/pipelineApi"
import { useProjeto } from "@/features/projetos/projetosApi"

const STATUS: readonly [StatusEtapa, string][] = [
  ["a_fazer", "A fazer"],
  ["em_andamento", "Em andamento"],
  ["aguardando_cliente", "Aguardando cliente"],
  ["concluida", "Concluída"],
]
const STATUS_LABEL = Object.fromEntries(STATUS) as Record<StatusEtapa, string>

function chipClass(s: StatusEtapa): string {
  if (s === "concluida") return "border-primary/40 bg-primary/5 text-primary"
  if (s === "em_andamento") return "border-primary/40 text-primary"
  if (s === "aguardando_cliente") return "border-primary/60 bg-primary/10 text-primary"
  return "border-border text-muted-foreground"
}

function fmt(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("pt-BR")
}

export function AndamentoPage() {
  const { projetoId = "" } = useParams()
  const projeto = useProjeto(projetoId)
  const pipeline = usePipeline(projetoId)
  const ehArquiteto = projeto.data?.meu_papel === "arquiteto"
  const [iniciarOpen, setIniciarOpen] = useState(false)
  const [editando, setEditando] = useState<string | null>(null)

  return (
    <div className="animate-fade-up">
      <Link
        to={`/projetos/${projetoId}`}
        className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronLeft className="size-4" />
        Projeto
      </Link>

      <div className="mb-6">
        <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Andamento do projeto</div>
        <h1 className="font-word text-3xl leading-tight break-words">{projeto.data?.nome ?? "…"}</h1>
      </div>

      {pipeline.isLoading ? (
        <CenteredSpinner />
      ) : pipeline.isError ? (
        <ErrorState
          message="Não foi possível carregar o andamento."
          onRetry={() => void pipeline.refetch()}
        />
      ) : (
        <ol className="space-y-2">
          {pipeline.data?.etapas.map((e, i) => (
            <EtapaItem
              key={e.etapa}
              etapa={e}
              numero={i + 1}
              ehArquiteto={ehArquiteto}
              projetoId={projetoId}
              editando={editando === e.etapa}
              onEditar={() => setEditando((v) => (v === e.etapa ? null : e.etapa))}
              onIniciar={() => setIniciarOpen(true)}
            />
          ))}
        </ol>
      )}

      <IniciarObraDialog projetoId={projetoId} open={iniciarOpen} onOpenChange={setIniciarOpen} />
    </div>
  )
}

function EtapaItem({
  etapa,
  numero,
  ehArquiteto,
  projetoId,
  editando,
  onEditar,
  onIniciar,
}: {
  etapa: EtapaProjeto
  numero: number
  ehArquiteto: boolean
  projetoId: string
  editando: boolean
  onEditar: () => void
  onIniciar: () => void
}) {
  const concluida = etapa.status === "concluida"
  return (
    <li
      className={cn(
        "rounded-2xl border bg-card p-4 transition-colors",
        etapa.acao_pendente ? "border-primary/50" : "border-border",
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "flex size-8 shrink-0 items-center justify-center rounded-full border text-sm font-medium",
            concluida ? "border-primary bg-primary text-primary-foreground" : "border-border text-muted-foreground",
          )}
        >
          {concluida ? <Check className="size-4" /> : numero}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-medium">{etapa.rotulo}</h2>
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide",
                chipClass(etapa.status),
              )}
            >
              {STATUS_LABEL[etapa.status]}
            </span>
          </div>

          {etapa.etapa === "medicao" && etapa.data_prevista && (
            <p className="mt-1 text-xs text-muted-foreground">
              Medição agendada para {fmt(etapa.data_prevista)}
            </p>
          )}
          {etapa.observacao && (
            <p className="mt-1 text-xs text-muted-foreground break-words">{etapa.observacao}</p>
          )}
          {etapa.etapa === "iniciar_obra" && etapa.decisao && (
            <p className="mt-1 text-xs font-medium text-primary">
              {etapa.decisao === "sim" ? "Cliente confirmou o início da obra" : "Cliente optou por não iniciar"}
            </p>
          )}

          {/* material da etapa: arquivos (PDF/imagem) e links — arquiteto cura, cliente vê */}
          <EtapaAnexos
            projetoId={projetoId}
            etapa={etapa.etapa}
            anexos={etapa.anexos}
            ehArquiteto={ehArquiteto}
          />

          {/* CLIENTE: ação pendente neste gate */}
          {!ehArquiteto && etapa.acao_pendente && (
            <div className="mt-2">
              {etapa.gate === "iniciar_obra" ? (
                <Button size="sm" onClick={onIniciar}>
                  Decidir início <ArrowRight className="size-4" />
                </Button>
              ) : (
                <Button asChild size="sm">
                  <Link to={`/projetos/${projetoId}/${etapa.gate === "proposta" ? "orcamento" : "revisoes"}`}>
                    {etapa.gate === "proposta" ? "Ver proposta" : "Ver e aprovar"}
                    <ArrowRight className="size-4" />
                  </Link>
                </Button>
              )}
            </div>
          )}

          {/* ARQUITETO: avançar a etapa */}
          {ehArquiteto && (
            <div className="mt-2">
              <Button variant="ghost" size="sm" onClick={onEditar} className="h-7 px-2 text-xs">
                <Pencil className="size-3.5" />
                {editando ? "Fechar" : "Editar"}
              </Button>
              {editando && (
                <EtapaEditor projetoId={projetoId} etapa={etapa} onClose={onEditar} />
              )}
            </div>
          )}
        </div>
      </div>
    </li>
  )
}

function EtapaEditor({
  projetoId,
  etapa,
  onClose,
}: {
  projetoId: string
  etapa: EtapaProjeto
  onClose: () => void
}) {
  const [status, setStatus] = useState<StatusEtapa>(etapa.status)
  const [data, setData] = useState<string | null>(etapa.data_prevista)
  const [obs, setObs] = useState(etapa.observacao ?? "")
  const mut = useAtualizarEtapa(projetoId)

  async function salvar() {
    if (mut.isPending) return
    const obsLimpa = obs.trim()
    try {
      await mut.mutateAsync({
        etapa: etapa.etapa,
        status,
        // só envia o que faz sentido (undefined = não enviado, o backend distingue de null)
        data_prevista: etapa.etapa === "medicao" ? data || null : undefined,
        observacao: obsLimpa === (etapa.observacao ?? "") ? undefined : obsLimpa || null,
      })
      toast.success("Etapa atualizada")
      onClose()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar.")
    }
  }

  return (
    <div className="mt-3 space-y-3 rounded-xl border border-border bg-background p-3">
      <div className="space-y-1.5">
        <Label className="text-xs">Status</Label>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as StatusEtapa)}
          className="h-9 w-full rounded-lg border border-border bg-card px-3 text-sm"
        >
          {STATUS.map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
      </div>
      {etapa.etapa === "medicao" && (
        <div className="space-y-1.5">
          <Label className="text-xs">Data da medição</Label>
          <Input type="date" value={data ?? ""} onChange={(e) => setData(e.target.value || null)} />
        </div>
      )}
      <div className="space-y-1.5">
        <Label className="text-xs">Observação / link (ex.: apresentação)</Label>
        <Input
          value={obs}
          onChange={(e) => setObs(e.target.value)}
          placeholder="Opcional — visível pro cliente"
        />
      </div>
      <Button size="sm" onClick={salvar} disabled={mut.isPending}>
        {mut.isPending && <Loader2 className="animate-spin" />}
        Salvar
      </Button>
    </div>
  )
}

function IniciarObraDialog({
  projetoId,
  open,
  onOpenChange,
}: {
  projetoId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const mut = useDecidirIniciarObra(projetoId)
  async function decidir(d: "sim" | "nao") {
    if (mut.isPending) return
    try {
      await mut.mutateAsync(d)
      onOpenChange(false)
      toast.success(d === "sim" ? "Tudo certo — vamos iniciar a obra!" : "Decisão registrada")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível registrar.")
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Iniciar a obra?</DialogTitle>
          <DialogDescription>
            Você aprovou o orçamento. Confirme se quer iniciar a obra agora — o arquiteto segue com a
            abertura.
          </DialogDescription>
        </DialogHeader>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => decidir("nao")} disabled={mut.isPending}>
            Ainda não
          </Button>
          <Button onClick={() => decidir("sim")} disabled={mut.isPending}>
            {mut.isPending ? <Loader2 className="animate-spin" /> : <Check />}
            Sim, iniciar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** Material da etapa: o arquiteto sobe ARQUIVOS (PDF/imagem) e LINKS; o cliente vê/abre. */
function EtapaAnexos({
  projetoId,
  etapa,
  anexos,
  ehArquiteto,
}: {
  projetoId: string
  etapa: string
  anexos: EtapaAnexo[]
  ehArquiteto: boolean
}) {
  const upload = useUploadEtapaArquivo(projetoId)
  const excluir = useExcluirEtapaAnexo(projetoId)
  const fileRef = useRef<HTMLInputElement>(null)
  const [lightbox, setLightbox] = useState<EtapaAnexo | null>(null)
  const [linkOpen, setLinkOpen] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<EtapaAnexo | null>(null)

  // cliente não vê seção vazia; o arquiteto sempre vê (pra poder anexar)
  if (anexos.length === 0 && !ehArquiteto) return null

  const arquivos = anexos.filter((a) => a.tipo === "arquivo")
  const links = anexos.filter((a) => a.tipo === "link")

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ""
    for (const f of files) {
      try {
        await upload.mutateAsync({ etapa, file: f })
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

  async function onConfirmDelete() {
    if (!pendingDelete) return
    try {
      await excluir.mutateAsync(pendingDelete.id)
      if (lightbox?.id === pendingDelete.id) setLightbox(null)
      setPendingDelete(null)
      toast.success("Removido")
    } catch {
      toast.error("Não foi possível remover.")
    }
  }

  return (
    <div className="mt-3 space-y-2">
      {arquivos.length > 0 && (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {arquivos.map((a) => (
            <AnexoTile
              key={a.id}
              projetoId={projetoId}
              anexo={a}
              ehArquiteto={ehArquiteto}
              onAbrir={() => (a.is_pdf ? void abrirAnexoPdf(projetoId, a) : setLightbox(a))}
              onExcluir={() => setPendingDelete(a)}
            />
          ))}
        </div>
      )}

      {links.length > 0 && (
        <ul className="space-y-1.5">
          {links.map((a) => (
            <li
              key={a.id}
              className="flex items-center gap-2 rounded-xl border border-border bg-card px-3 py-2"
            >
              <Link2 className="size-4 shrink-0 text-muted-foreground" />
              <a
                href={a.url ?? "#"}
                target="_blank"
                rel="noopener noreferrer"
                className="min-w-0 flex-1 truncate text-sm text-primary hover:underline"
              >
                {a.label || a.url}
              </a>
              <ExternalLink className="size-3.5 shrink-0 text-muted-foreground" />
              {ehArquiteto && (
                <button
                  type="button"
                  onClick={() => setPendingDelete(a)}
                  aria-label="Remover link"
                  className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:text-destructive"
                >
                  <Trash2 className="size-3.5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {ehArquiteto && (
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-7 px-2 text-xs"
            disabled={upload.isPending}
            onClick={() => fileRef.current?.click()}
          >
            {upload.isPending ? <Loader2 className="animate-spin" /> : <Paperclip className="size-3.5" />}
            Arquivo
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-7 px-2 text-xs"
            onClick={() => setLinkOpen(true)}
          >
            <Link2 className="size-3.5" />
            Link
          </Button>
        </div>
      )}

      <input
        ref={fileRef}
        type="file"
        accept="image/*,application/pdf"
        multiple
        className="hidden"
        onChange={onPick}
      />

      <Dialog open={lightbox !== null} onOpenChange={(o) => !o && setLightbox(null)}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle className="truncate text-lg">{lightbox?.label || lightbox?.nome_arquivo}</DialogTitle>
          </DialogHeader>
          {lightbox && (
            <AnexoImage
              path={conteudoEtapaAnexoPath(projetoId, lightbox.id, "full")}
              alt={lightbox.nome_arquivo ?? "anexo"}
              fit="contain"
              className="max-h-[70vh] w-full rounded-xl bg-black/30"
            />
          )}
        </DialogContent>
      </Dialog>

      <AddLinkDialog projetoId={projetoId} etapa={etapa} open={linkOpen} onOpenChange={setLinkOpen} />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title="Remover material?"
        description={
          pendingDelete ? `"${pendingDelete.label || pendingDelete.nome_arquivo || pendingDelete.url}" será removido.` : undefined
        }
        pending={excluir.isPending}
        onConfirm={onConfirmDelete}
      />
    </div>
  )
}

function AnexoTile({
  projetoId,
  anexo,
  ehArquiteto,
  onAbrir,
  onExcluir,
}: {
  projetoId: string
  anexo: EtapaAnexo
  ehArquiteto: boolean
  onAbrir: () => void
  onExcluir: () => void
}) {
  return (
    <div className="group relative aspect-square overflow-hidden rounded-xl border border-border">
      <button type="button" onClick={onAbrir} className="size-full" title={anexo.label || anexo.nome_arquivo || ""}>
        {anexo.is_pdf ? (
          <span className="flex size-full flex-col items-center justify-center gap-1 bg-accent/40 text-muted-foreground">
            <FileText className="size-6" />
            <span className="px-1 text-[10px]">PDF</span>
          </span>
        ) : (
          <AnexoImage
            path={conteudoEtapaAnexoPath(projetoId, anexo.id, "thumb")}
            alt={anexo.nome_arquivo ?? "anexo"}
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

function AddLinkDialog({
  projetoId,
  etapa,
  open,
  onOpenChange,
}: {
  projetoId: string
  etapa: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [url, setUrl] = useState("")
  const [label, setLabel] = useState("")
  const add = useAdicionarEtapaLink(projetoId)
  const valido = /^https?:\/\/\S+/i.test(url.trim())

  function close(o: boolean) {
    if (!o) {
      setUrl("")
      setLabel("")
    }
    onOpenChange(o)
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || add.isPending) return
    try {
      await add.mutateAsync({ etapa, url, label })
      toast.success("Link adicionado")
      close(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível adicionar o link.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Adicionar link</DialogTitle>
          <DialogDescription>
            Cole um link que o cliente possa abrir — tour 3D, vídeo, pasta de arquivos…
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="anexo-url">Link (URL)</Label>
            <Input
              id="anexo-url"
              type="url"
              inputMode="url"
              value={url}
              maxLength={2000}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://…"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="anexo-label">Rótulo (opcional)</Label>
            <Input
              id="anexo-label"
              value={label}
              maxLength={200}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Ex.: Tour 3D"
            />
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => close(false)}>
              Cancelar
            </Button>
            <Button type="submit" className="flex-1" disabled={!valido || add.isPending}>
              {add.isPending && <Loader2 className="animate-spin" />}
              Adicionar
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Abre um PDF de anexo de etapa em nova aba (fetch autenticado → blob URL). */
async function abrirAnexoPdf(projetoId: string, anexo: EtapaAnexo) {
  try {
    const blob = await api.getBlob(conteudoEtapaAnexoPath(projetoId, anexo.id, "full"))
    const url = URL.createObjectURL(blob)
    window.open(url, "_blank", "noopener,noreferrer")
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch {
    toast.error("Não foi possível abrir o PDF.")
  }
}
