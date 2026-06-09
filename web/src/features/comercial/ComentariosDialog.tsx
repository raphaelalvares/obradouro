import { Check, Loader2, Pencil, Send, Trash2, X } from "lucide-react"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { CenteredSpinner } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { ApiError } from "@/lib/api"
import {
  useAddComentario,
  useComentarios,
  useEditComentario,
  useExcluirComentario,
  type Comentario,
  type Oportunidade,
} from "@/features/comercial/comercialApi"

const fmt = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
})

export function ComentariosDialog({
  open,
  onOpenChange,
  oportunidade,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  oportunidade: Oportunidade | null
}) {
  const opId = oportunidade?.id ?? ""
  const comentarios = useComentarios(opId)
  const add = useAddComentario(opId)
  const [texto, setTexto] = useState("")

  if (!oportunidade) return null

  async function enviar(e: FormEvent) {
    e.preventDefault()
    const t = texto.trim()
    if (!t || add.isPending) return
    try {
      await add.mutateAsync(t)
      setTexto("")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar o comentário.")
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) setTexto("")
        onOpenChange(o)
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Comentários</DialogTitle>
          <DialogDescription className="break-words">
            #{oportunidade.seq_humano ?? "—"} · {oportunidade.nome}
          </DialogDescription>
        </DialogHeader>

        {/* captura rápida no topo */}
        <form onSubmit={enviar} className="space-y-2">
          <Textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder="Anote algo da negociação…"
            className="min-h-[60px]"
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === "Enter") void enviar(e)
            }}
          />
          <div className="flex justify-end">
            <Button type="submit" size="sm" disabled={!texto.trim() || add.isPending}>
              {add.isPending ? <Loader2 className="animate-spin" /> : <Send />}
              Adicionar
            </Button>
          </div>
        </form>

        {/* timeline */}
        <div className="-mx-1 max-h-[48vh] space-y-2 overflow-y-auto px-1">
          {comentarios.isLoading && <CenteredSpinner />}
          {comentarios.isSuccess && comentarios.data.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Nenhum comentário ainda.
            </p>
          )}
          {comentarios.data?.map((c) => (
            <ComentarioItem key={c.id} opId={opId} comentario={c} />
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function ComentarioItem({ opId, comentario }: { opId: string; comentario: Comentario }) {
  const editar = useEditComentario(opId)
  const excluir = useExcluirComentario(opId)
  const [editando, setEditando] = useState(false)
  const [texto, setTexto] = useState(comentario.texto)
  const [confirmando, setConfirmando] = useState(false)

  async function salvar() {
    const t = texto.trim()
    if (!t || editar.isPending) return
    try {
      await editar.mutateAsync({ id: comentario.id, texto: t })
      setEditando(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível editar.")
    }
  }

  async function remover() {
    try {
      await excluir.mutateAsync(comentario.id)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível excluir.")
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <div className="mb-1 flex items-center gap-2 text-[11px] text-muted-foreground">
        <span className="truncate">{comentario.autor_nome ?? "—"}</span>
        <span>·</span>
        <span className="shrink-0">{fmt.format(new Date(comentario.created_at))}</span>
        {comentario.updated_at !== comentario.created_at && (
          <span className="shrink-0 opacity-70">(editado)</span>
        )}
        {!editando && !confirmando && (
          <div className="ml-auto flex shrink-0 gap-1">
            <button
              type="button"
              aria-label="Editar"
              className="rounded p-1 text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => {
                setTexto(comentario.texto)
                setEditando(true)
              }}
            >
              <Pencil className="size-3.5" />
            </button>
            <button
              type="button"
              aria-label="Excluir"
              className="rounded p-1 text-muted-foreground transition-colors hover:text-destructive"
              onClick={() => setConfirmando(true)}
            >
              <Trash2 className="size-3.5" />
            </button>
          </div>
        )}
      </div>

      {editando ? (
        <div className="space-y-2">
          <Textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            className="min-h-[56px]"
          />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setEditando(false)}>
              Cancelar
            </Button>
            <Button type="button" size="sm" disabled={!texto.trim() || editar.isPending} onClick={salvar}>
              {editar.isPending && <Loader2 className="animate-spin" />}
              Salvar
            </Button>
          </div>
        </div>
      ) : confirmando ? (
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm">Excluir este comentário?</span>
          <div className="flex shrink-0 gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setConfirmando(false)}>
              <X />
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={excluir.isPending}
              onClick={remover}
            >
              {excluir.isPending ? <Loader2 className="animate-spin" /> : <Check />}
            </Button>
          </div>
        </div>
      ) : (
        <p className="whitespace-pre-wrap break-words text-sm">{comentario.texto}</p>
      )}
    </div>
  )
}
