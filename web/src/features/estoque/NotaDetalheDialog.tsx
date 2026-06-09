import { ArrowDown, ArrowUp, Check, Loader2, PencilLine, Trash2 } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { CenteredSpinner } from "@/components/feedback/states"
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
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import {
  useAtualizarNota,
  useConferirItem,
  useEditarNomeItem,
  useExcluirNota,
  useNota,
  type NotaItem,
} from "@/features/estoque/estoqueApi"

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })
const num = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 })

/** Divergência da conferência: null = conferido e bateu (ou não conferido). */
function divergenciaDe(item: NotaItem): { faltou: boolean; abs: number } | null {
  const c = item.quantidade_conferida
  if (c == null || c === item.quantidade_nota) return null
  const diff = c - item.quantidade_nota
  return { faltou: diff < 0, abs: Math.abs(diff) }
}

export function NotaDetalheDialog({
  obraId,
  notaId,
  ehArquiteto,
  podeConferir,
  onOpenChange,
}: {
  obraId: string
  notaId: string | null
  ehArquiteto: boolean
  podeConferir: boolean
  onOpenChange: (open: boolean) => void
}) {
  const open = notaId !== null
  const nota = useNota(obraId, notaId)
  const atualizar = useAtualizarNota(obraId)
  const excluir = useExcluirNota(obraId)
  const [confirmar, setConfirmar] = useState(false)

  async function onExcluir() {
    if (!notaId) return
    try {
      await excluir.mutateAsync(notaId)
      toast.success("Nota removida")
      setConfirmar(false)
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível remover.")
    }
  }

  const d = nota.data

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="truncate">
            {d?.numero ? `NF ${d.numero}` : "Nota fiscal"}
            {d?.seq_humano != null && (
              <span className="ml-2 font-display text-sm text-muted-foreground">#{d.seq_humano}</span>
            )}
          </DialogTitle>
          <DialogDescription className="truncate">
            {d?.emitente_nome || "Emitente não informado"}
          </DialogDescription>
        </DialogHeader>

        {nota.isLoading || !d ? (
          <CenteredSpinner />
        ) : (
          <div className="-mr-3 max-h-[65vh] space-y-4 overflow-y-auto pr-3">
            {/* cabeçalho de info */}
            <div className="grid grid-cols-2 gap-3 text-sm">
              <Info label="Valor total" value={brl.format(d.valor_total)} />
              <Info
                label="Emissão"
                value={d.data_emissao ? new Date(d.data_emissao).toLocaleDateString("pt-BR") : "—"}
              />
              <div className="col-span-2">
                <div className="text-xs uppercase tracking-wider text-muted-foreground">
                  Data de chegada
                </div>
                {ehArquiteto ? (
                  <Input
                    type="date"
                    className="mt-1"
                    value={d.data_chegada ?? ""}
                    onChange={(e) =>
                      atualizar.mutate({ notaId: d.id, data_chegada: e.target.value || null })
                    }
                  />
                ) : (
                  <div className="mt-1 text-sm">
                    {d.data_chegada
                      ? new Date(`${d.data_chegada}T00:00:00`).toLocaleDateString("pt-BR")
                      : "—"}
                  </div>
                )}
              </div>
              {d.chave_acesso && (
                <div className="col-span-2">
                  <div className="text-xs uppercase tracking-wider text-muted-foreground">Chave</div>
                  <div className="mt-0.5 break-all font-display text-xs text-muted-foreground">
                    {d.chave_acesso}
                  </div>
                </div>
              )}
            </div>

            {/* itens */}
            <div>
              <div className="mb-2 text-xs uppercase tracking-wider text-muted-foreground">
                Itens ({d.itens.length})
              </div>
              <ul className="space-y-2">
                {d.itens.map((it) => (
                  <ItemRow
                    key={it.id}
                    obraId={obraId}
                    notaId={d.id}
                    item={it}
                    ehArquiteto={ehArquiteto}
                    podeConferir={podeConferir}
                  />
                ))}
              </ul>
            </div>

            {ehArquiteto && (
              <Button
                variant="outline"
                className="w-full text-destructive hover:bg-destructive/10 hover:text-destructive"
                onClick={() => setConfirmar(true)}
              >
                <Trash2 />
                Excluir nota
              </Button>
            )}
          </div>
        )}

        <ConfirmDialog
          open={confirmar}
          onOpenChange={setConfirmar}
          title="Excluir nota?"
          description="A nota e seus itens serão removidos do estoque. Não pode ser desfeito."
          pending={excluir.isPending}
          onConfirm={onExcluir}
        />
      </DialogContent>
    </Dialog>
  )
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="mt-1">{value}</div>
    </div>
  )
}

function ItemRow({
  obraId,
  notaId,
  item,
  ehArquiteto,
  podeConferir,
}: {
  obraId: string
  notaId: string
  item: NotaItem
  ehArquiteto: boolean
  podeConferir: boolean
}) {
  const conferir = useConferirItem(obraId, notaId)
  const editarNome = useEditarNomeItem(obraId, notaId)
  const [editando, setEditando] = useState(false)
  const [nome, setNome] = useState(item.nome_editado ?? "")

  async function salvarNome() {
    setEditando(false)
    const novo = nome.trim() || null
    if (novo === (item.nome_editado ?? null)) return
    try {
      await editarNome.mutateAsync({ itemId: item.id, nome_editado: novo })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar o nome.")
    }
  }

  const dv = divergenciaDe(item)

  return (
    <li
      className={cn(
        "rounded-xl border p-3",
        dv
          ? dv.faltou
            ? "border-destructive/50 bg-destructive/5"
            : "border-amber-500/50 bg-amber-500/5"
          : "border-border bg-card",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {editando ? (
            <Input
              value={nome}
              maxLength={300}
              placeholder={item.descricao}
              onChange={(e) => setNome(e.target.value)}
              onBlur={salvarNome}
              onKeyDown={(e) => e.key === "Enter" && salvarNome()}
            />
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="min-w-0 break-words text-sm font-medium">{item.nome}</span>
              {ehArquiteto && (
                <button
                  type="button"
                  onClick={() => {
                    setNome(item.nome_editado ?? "")
                    setEditando(true)
                  }}
                  aria-label="Editar nome"
                  className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
                >
                  <PencilLine className="size-3.5" />
                </button>
              )}
            </div>
          )}
          <div className="mt-0.5 text-xs text-muted-foreground">
            {item.codigo ? `${item.codigo} · ` : ""}
            nota: {num.format(item.quantidade_nota)} {item.unidade ?? ""}
            {item.valor_total != null ? ` · ${brl.format(item.valor_total)}` : ""}
          </div>
          {dv && (
            <div
              className={cn(
                "mt-0.5 text-xs font-medium",
                dv.faltou ? "text-destructive" : "text-amber-600",
              )}
            >
              {dv.faltou ? "faltou" : "sobrou"} {num.format(dv.abs)} {item.unidade ?? ""}
            </div>
          )}
        </div>

        <div className="shrink-0 text-right">
          {podeConferir ? (
            <ConferirInput
              item={item}
              pending={conferir.isPending}
              onConferir={(q) => conferir.mutate({ itemId: item.id, quantidade_conferida: q })}
            />
          ) : (
            <ConferenciaLeitura item={item} />
          )}
        </div>
      </div>
    </li>
  )
}

function ConferirInput({
  item,
  pending,
  onConferir,
}: {
  item: NotaItem
  pending: boolean
  onConferir: (q: number | null) => void
}) {
  const [val, setVal] = useState(item.quantidade_conferida?.toString() ?? "")
  const dv = divergenciaDe(item)

  function commit() {
    const q = val.trim() === "" ? null : Number(val.replace(",", "."))
    if (q !== null && Number.isNaN(q)) {
      setVal(item.quantidade_conferida?.toString() ?? "")
      return
    }
    if (q === (item.quantidade_conferida ?? null)) return
    onConferir(q)
  }

  return (
    <div className="flex items-center gap-1.5">
      {pending ? (
        <Loader2 className="size-4 animate-spin text-muted-foreground" />
      ) : item.quantidade_conferida == null ? null : dv ? (
        dv.faltou ? (
          <ArrowDown className="size-4 text-destructive" />
        ) : (
          <ArrowUp className="size-4 text-amber-600" />
        )
      ) : (
        <Check className="size-4 text-primary" />
      )}
      <Input
        inputMode="decimal"
        value={val}
        placeholder="contar"
        className="h-9 w-20 text-right"
        onChange={(e) => setVal(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      />
    </div>
  )
}

function ConferenciaLeitura({ item }: { item: NotaItem }) {
  if (item.quantidade_conferida == null) {
    return <span className="text-xs text-muted-foreground">não conferido</span>
  }
  const dv = divergenciaDe(item)
  return (
    <div
      className={cn(
        "text-sm",
        dv ? (dv.faltou ? "text-destructive" : "text-amber-600") : "text-primary",
      )}
    >
      {num.format(item.quantidade_conferida)} {item.unidade ?? ""}
      {dv && (
        <div className="text-[10px] uppercase">
          {dv.faltou ? "faltou" : "sobrou"} {num.format(dv.abs)}
        </div>
      )}
    </div>
  )
}
