import { Camera, ImagePlus, Loader2, Trash2 } from "lucide-react"
import { useEffect, useRef, useState } from "react"
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
import { AnexoImage } from "@/features/anexos/AnexoImage"
import {
  conteudoPath,
  useAnexos,
  useEditarLegenda,
  useExcluirAnexo,
  useUploadAnexo,
  type Anexo,
  type ParentType,
} from "@/features/anexos/anexosApi"
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"

export interface FotosTarget {
  parentType: ParentType
  parentId: string
  titulo: string
}

export function FotosDialog({
  obraId,
  target,
  readOnly = false,
  onOpenChange,
}: {
  obraId: string
  target: FotosTarget | null
  /** true = só leitura (cliente): esconde adicionar/excluir; a galeria/lightbox seguem visíveis. */
  readOnly?: boolean
  onOpenChange: (open: boolean) => void
}) {
  const open = target !== null
  const parentType = target?.parentType ?? "checklist_item"
  const parentId = target?.parentId ?? ""

  const anexos = useAnexos(obraId, parentType, parentId, open)
  const upload = useUploadAnexo(obraId, parentType, parentId)
  const excluir = useExcluirAnexo(obraId, parentType, parentId)
  const editarLegenda = useEditarLegenda(obraId, parentType, parentId)

  const fileRef = useRef<HTMLInputElement>(null)
  const [lightbox, setLightbox] = useState<Anexo | null>(null)
  const [pendingDelete, setPendingDelete] = useState<Anexo | null>(null)
  const [legendaDraft, setLegendaDraft] = useState("")
  // reabastece o rascunho da legenda ao trocar de foto no lightbox (não reseta após salvar: mesmo id).
  useEffect(() => setLegendaDraft(lightbox?.legenda ?? ""), [lightbox?.id])

  async function onSalvarLegenda() {
    if (!lightbox) return
    const nova = legendaDraft.trim() || null
    try {
      const upd = await editarLegenda.mutateAsync({ anexoId: lightbox.id, legenda: nova })
      setLightbox(upd)
      toast.success("Legenda salva")
    } catch {
      toast.error("Não foi possível salvar a legenda.")
    }
  }

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    e.target.value = "" // permite re-selecionar o mesmo arquivo
    for (const f of files) {
      try {
        await upload.mutateAsync(f)
      } catch (err) {
        if (err instanceof ApiError && err.isUpgrade) {
          toast.error(err.problem?.detail ?? "Armazenamento do plano esgotado.")
          break // não insistir nos próximos se a quota estourou
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
      await excluir.mutateAsync(pendingDelete.id)
      if (lightbox?.id === pendingDelete.id) setLightbox(null)
      setPendingDelete(null)
      toast.success("Foto excluída")
    } catch {
      toast.error("Não foi possível excluir a foto.")
    }
  }

  const lista = anexos.data ?? []

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Fotos</DialogTitle>
            <DialogDescription className="truncate">{target?.titulo}</DialogDescription>
          </DialogHeader>

          <div className="max-h-[55vh] overflow-y-auto">
            {anexos.isLoading && <CenteredSpinner />}
            {anexos.isError && (
              <ErrorState
                message="Não foi possível carregar as fotos."
                onRetry={() => void anexos.refetch()}
              />
            )}
            {anexos.isSuccess && lista.length === 0 && (
              <EmptyState
                icon={Camera}
                title="Sem fotos ainda"
                description="Registre o andamento com uma foto direto do celular."
              />
            )}
            {lista.length > 0 && (
              <div className="grid grid-cols-3 gap-2">
                {lista.map((a) => (
                  <div key={a.id} className="group relative aspect-square overflow-hidden rounded-xl border border-border">
                    <button
                      type="button"
                      onClick={() => setLightbox(a)}
                      className="size-full"
                      title={a.nome_arquivo}
                    >
                      <AnexoImage
                        path={conteudoPath(obraId, a.id, "thumb")}
                        alt={a.legenda || a.nome_arquivo}
                        className="size-full"
                      />
                    </button>
                    {a.legenda && (
                      <div className="pointer-events-none absolute inset-x-0 bottom-0 line-clamp-2 bg-black/55 px-1.5 py-0.5 text-[10px] leading-tight text-white/90">
                        {a.legenda}
                      </div>
                    )}
                    {!readOnly && (
                      <button
                        type="button"
                        onClick={() => setPendingDelete(a)}
                        aria-label="Excluir foto"
                        className="absolute right-1 top-1 rounded-lg bg-black/55 p-1.5 text-white/90 opacity-0 transition-opacity hover:bg-destructive group-hover:opacity-100"
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {!readOnly && (
            <>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={onPick}
              />
              <Button
                type="button"
                className="w-full"
                disabled={upload.isPending}
                onClick={() => fileRef.current?.click()}
              >
                {upload.isPending ? <Loader2 className="animate-spin" /> : <ImagePlus />}
                {upload.isPending ? "Enviando…" : "Adicionar foto"}
              </Button>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Lightbox: visualização do 'full' */}
      <Dialog open={lightbox !== null} onOpenChange={(o) => !o && setLightbox(null)}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle className="truncate text-lg">{lightbox?.nome_arquivo}</DialogTitle>
            {lightbox && (
              <DialogDescription>
                {lightbox.largura && lightbox.altura ? `${lightbox.largura}×${lightbox.altura} · ` : ""}
                {Math.round((lightbox.tamanho_bytes / 1024) * 10) / 10} KB
                {lightbox.criado_por_nome ? ` · por ${lightbox.criado_por_nome}` : ""}
              </DialogDescription>
            )}
          </DialogHeader>
          {lightbox && (
            <AnexoImage
              path={conteudoPath(obraId, lightbox.id, "full")}
              alt={lightbox.legenda || lightbox.nome_arquivo}
              fit="contain"
              className={cn("max-h-[70vh] w-full rounded-xl bg-black/30")}
            />
          )}
          {/* legenda: editável p/ quem executa, texto p/ quem só lê */}
          {lightbox && !readOnly && (
            <div className="flex items-center gap-2">
              <Input
                value={legendaDraft}
                onChange={(e) => setLegendaDraft(e.target.value)}
                maxLength={300}
                placeholder="Legenda da foto…"
                className="flex-1"
              />
              <Button
                type="button"
                variant="outline"
                disabled={editarLegenda.isPending || legendaDraft === (lightbox.legenda ?? "")}
                onClick={onSalvarLegenda}
              >
                {editarLegenda.isPending ? <Loader2 className="animate-spin" /> : "Salvar"}
              </Button>
            </div>
          )}
          {lightbox && readOnly && lightbox.legenda && (
            <p className="text-sm text-muted-foreground">{lightbox.legenda}</p>
          )}
          {!readOnly && (
            <Button
              type="button"
              variant="outline"
              className="w-full text-destructive hover:bg-destructive/10 hover:text-destructive"
              onClick={() => lightbox && setPendingDelete(lightbox)}
            >
              <Trash2 />
              Excluir foto
            </Button>
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title="Excluir foto?"
        description={<>"{pendingDelete?.nome_arquivo}" será removida. Esta ação não pode ser desfeita.</>}
        pending={excluir.isPending}
        onConfirm={onConfirmDelete}
      />
    </>
  )
}
