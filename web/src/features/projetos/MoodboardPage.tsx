import { ChevronLeft, ImagePlus, LayoutGrid, Loader2, Plus, Trash2 } from "lucide-react"
import { useRef, useState, type FormEvent } from "react"
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"

import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { AnexoImage } from "@/features/anexos/AnexoImage"
import { ApiError } from "@/lib/api"
import {
  itemMoodboardPath,
  useCriarSecao,
  useExcluirItem,
  useExcluirSecao,
  useItens,
  useProjeto,
  useSecoes,
  useUploadItem,
  type MoodboardItem,
  type Secao,
} from "@/features/projetos/projetosApi"

export function MoodboardPage() {
  const { projetoId = "" } = useParams()
  const projeto = useProjeto(projetoId)
  const secoes = useSecoes(projetoId)
  const itens = useItens(projetoId)
  const upload = useUploadItem(projetoId)
  const excluirItem = useExcluirItem(projetoId)

  const ehArquiteto = projeto.data?.meu_papel === "arquiteto"
  const fileRef = useRef<HTMLInputElement>(null)
  const alvoSecao = useRef<string | null>(null)
  const [lightbox, setLightbox] = useState<MoodboardItem | null>(null)
  const [pendingDelete, setPendingDelete] = useState<MoodboardItem | null>(null)

  function pedirUpload(secaoId: string | null) {
    alvoSecao.current = secaoId
    fileRef.current?.click()
  }

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ""
    for (const f of files) {
      try {
        await upload.mutateAsync({ file: f, secaoId: alvoSecao.current })
      } catch (err) {
        if (err instanceof ApiError && err.isUpgrade) {
          toast.error(err.problem?.detail ?? "Armazenamento do plano esgotado.")
          break
        } else if (err instanceof ApiError && err.status === 415) {
          toast.error(`"${f.name}" não é uma imagem suportada.`)
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
      await excluirItem.mutateAsync(pendingDelete.id)
      if (lightbox?.id === pendingDelete.id) setLightbox(null)
      setPendingDelete(null)
      toast.success("Imagem removida")
    } catch {
      toast.error("Não foi possível remover.")
    }
  }

  const listaItens = itens.data ?? []
  const listaSecoes = secoes.data ?? []
  const semSecao = listaItens.filter((i) => !i.secao_id)
  const carregando = projeto.isLoading || secoes.isLoading || itens.isLoading
  const vazio = listaItens.length === 0 && listaSecoes.length === 0

  return (
    <div className="animate-fade-up">
      <Link
        to={`/projetos/${projetoId}`}
        className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronLeft className="size-4" />
        {projeto.data?.nome ?? "Projeto"}
      </Link>

      <div className="mb-6 flex items-end justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Referências</div>
          <h1 className="font-word text-4xl leading-none">MOODBOARD</h1>
        </div>
        {ehArquiteto && !vazio && (
          <Button disabled={upload.isPending} onClick={() => pedirUpload(null)}>
            {upload.isPending ? <Loader2 className="animate-spin" /> : <ImagePlus />}
            Imagem
          </Button>
        )}
      </div>

      {carregando && <CenteredSpinner />}
      {itens.isError && (
        <ErrorState message="Não foi possível carregar o moodboard." onRetry={() => void itens.refetch()} />
      )}

      {!carregando && vazio && (
        <EmptyState
          icon={LayoutGrid}
          title="Moodboard vazio"
          description={
            ehArquiteto
              ? "Adicione imagens de referência e organize em seções (ex.: Sala, Cozinha)."
              : "O arquiteto ainda não adicionou referências."
          }
          action={
            ehArquiteto ? (
              <Button disabled={upload.isPending} onClick={() => pedirUpload(null)}>
                <ImagePlus />
                Adicionar imagem
              </Button>
            ) : undefined
          }
        />
      )}

      {!carregando && !vazio && (
        <div className="space-y-8">
          {listaSecoes.map((s) => (
            <SecaoBloco
              key={s.id}
              projetoId={projetoId}
              secao={s}
              itens={listaItens.filter((i) => i.secao_id === s.id)}
              ehArquiteto={ehArquiteto}
              onUpload={() => pedirUpload(s.id)}
              onAbrir={setLightbox}
              onExcluir={setPendingDelete}
            />
          ))}

          {(semSecao.length > 0 || listaSecoes.length === 0) && (
            <Grupo
              titulo={listaSecoes.length === 0 ? null : "Sem seção"}
              itens={semSecao}
              projetoId={projetoId}
              ehArquiteto={ehArquiteto}
              onUpload={() => pedirUpload(null)}
              onAbrir={setLightbox}
              onExcluir={setPendingDelete}
            />
          )}

          {ehArquiteto && <NovaSecaoInline projetoId={projetoId} ordem={listaSecoes.length} />}
        </div>
      )}

      <input ref={fileRef} type="file" accept="image/*" multiple className="hidden" onChange={onPick} />

      {/* Lightbox */}
      <Dialog open={lightbox !== null} onOpenChange={(o) => !o && setLightbox(null)}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle className="truncate text-lg">
              {lightbox?.legenda || lightbox?.nome_arquivo}
            </DialogTitle>
          </DialogHeader>
          {lightbox && (
            <AnexoImage
              path={itemMoodboardPath(projetoId, lightbox.id, "full")}
              alt={lightbox.legenda || lightbox.nome_arquivo}
              fit="contain"
              className="max-h-[70vh] w-full rounded-xl bg-black/30"
            />
          )}
          {ehArquiteto && lightbox && (
            <Button
              variant="outline"
              className="w-full text-destructive hover:bg-destructive/10 hover:text-destructive"
              onClick={() => setPendingDelete(lightbox)}
            >
              <Trash2 />
              Remover imagem
            </Button>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title="Remover imagem?"
        description="Esta ação não pode ser desfeita."
        pending={excluirItem.isPending}
        onConfirm={onConfirmDelete}
      />
    </div>
  )
}

function SecaoBloco({
  projetoId,
  secao,
  itens,
  ehArquiteto,
  onUpload,
  onAbrir,
  onExcluir,
}: {
  projetoId: string
  secao: Secao
  itens: MoodboardItem[]
  ehArquiteto: boolean
  onUpload: () => void
  onAbrir: (i: MoodboardItem) => void
  onExcluir: (i: MoodboardItem) => void
}) {
  const excluirSecao = useExcluirSecao(projetoId)
  const [confirmar, setConfirmar] = useState(false)

  async function onConfirmDelete() {
    try {
      await excluirSecao.mutateAsync(secao.id)
      setConfirmar(false)
      toast.success("Seção removida")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível remover a seção.")
    }
  }

  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-medium">
          {secao.nome}
          <span className="ml-2 text-xs text-muted-foreground">{itens.length}</span>
        </h2>
        {ehArquiteto && (
          <button
            type="button"
            onClick={() => setConfirmar(true)}
            aria-label="Remover seção"
            className="text-muted-foreground transition-colors hover:text-destructive"
          >
            <Trash2 className="size-4" />
          </button>
        )}
      </div>
      <Grade
        itens={itens}
        projetoId={projetoId}
        ehArquiteto={ehArquiteto}
        onUpload={onUpload}
        onAbrir={onAbrir}
        onExcluir={onExcluir}
      />
      <ConfirmDialog
        open={confirmar}
        onOpenChange={setConfirmar}
        title={`Remover "${secao.nome}"?`}
        description="As imagens desta seção também serão removidas."
        pending={excluirSecao.isPending}
        onConfirm={onConfirmDelete}
      />
    </section>
  )
}

function Grupo({
  titulo,
  itens,
  projetoId,
  ehArquiteto,
  onUpload,
  onAbrir,
  onExcluir,
}: {
  titulo: string | null
  itens: MoodboardItem[]
  projetoId: string
  ehArquiteto: boolean
  onUpload: () => void
  onAbrir: (i: MoodboardItem) => void
  onExcluir: (i: MoodboardItem) => void
}) {
  return (
    <section>
      {titulo && <h2 className="mb-2 text-sm font-medium text-muted-foreground">{titulo}</h2>}
      <Grade
        itens={itens}
        projetoId={projetoId}
        ehArquiteto={ehArquiteto}
        onUpload={onUpload}
        onAbrir={onAbrir}
        onExcluir={onExcluir}
      />
    </section>
  )
}

function Grade({
  itens,
  projetoId,
  ehArquiteto,
  onUpload,
  onAbrir,
  onExcluir,
}: {
  itens: MoodboardItem[]
  projetoId: string
  ehArquiteto: boolean
  onUpload: () => void
  onAbrir: (i: MoodboardItem) => void
  onExcluir: (i: MoodboardItem) => void
}) {
  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
      {ehArquiteto && (
        <button
          type="button"
          onClick={onUpload}
          className="flex aspect-square items-center justify-center rounded-xl border border-dashed border-border text-muted-foreground transition-colors hover:border-primary/50 hover:text-primary"
        >
          <ImagePlus className="size-5" />
        </button>
      )}
      {itens.map((it) => (
        <div key={it.id} className="group relative aspect-square overflow-hidden rounded-xl border border-border">
          <button type="button" onClick={() => onAbrir(it)} className="size-full" title={it.legenda || it.nome_arquivo}>
            <AnexoImage
              path={itemMoodboardPath(projetoId, it.id, "thumb")}
              alt={it.legenda || it.nome_arquivo}
              className="size-full"
            />
          </button>
          {ehArquiteto && (
            <button
              type="button"
              onClick={() => onExcluir(it)}
              aria-label="Remover imagem"
              className="absolute right-1 top-1 rounded-lg bg-black/55 p-1.5 text-white/90 opacity-0 transition-opacity hover:bg-destructive group-hover:opacity-100"
            >
              <Trash2 className="size-3.5" />
            </button>
          )}
        </div>
      ))}
    </div>
  )
}

function NovaSecaoInline({ projetoId, ordem }: { projetoId: string; ordem: number }) {
  const [aberto, setAberto] = useState(false)
  const [nome, setNome] = useState("")
  const criar = useCriarSecao(projetoId)
  const valido = nome.trim().length > 0

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || criar.isPending) return
    try {
      await criar.mutateAsync({ nome, ordem })
      setNome("")
      setAberto(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível criar a seção.")
    }
  }

  if (!aberto) {
    return (
      <Button variant="outline" size="sm" onClick={() => setAberto(true)}>
        <Plus />
        Nova seção
      </Button>
    )
  }

  return (
    <form onSubmit={onSubmit} className="flex gap-2">
      <Input
        autoFocus
        value={nome}
        maxLength={120}
        onChange={(e) => setNome(e.target.value)}
        onBlur={() => !nome && setAberto(false)}
        placeholder="Nome da seção (ex.: Sala)"
      />
      <Button type="submit" disabled={!valido || criar.isPending}>
        {criar.isPending ? <Loader2 className="animate-spin" /> : "Criar"}
      </Button>
    </form>
  )
}
