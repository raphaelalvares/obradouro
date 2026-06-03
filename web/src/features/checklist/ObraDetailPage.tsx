import { ChevronLeft, ListChecks, Plus, Trash2, Upload } from "lucide-react"
import { useState, type FormEvent } from "react"
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"

import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Input } from "@/components/ui/input"
import {
  useChecklist,
  useCriarItem,
  useExcluirEtapa,
  useExcluirItem,
  useToggleItem,
  type EstadoItem,
  type Etapa,
  type Item,
} from "@/features/checklist/checklistApi"
import { CriarEtapaDialog } from "@/features/checklist/CriarEtapaDialog"
import { ImportarChecklistDialog } from "@/features/checklist/ImportarChecklistDialog"
import { StateToggle } from "@/features/checklist/StateToggle"
import { useObra } from "@/features/obras/obrasApi"

type PendingDelete =
  | { kind: "etapa"; id: string; label: string; count: number }
  | { kind: "item"; id: string; label: string }
  | null

export function ObraDetailPage() {
  const { obraId = "" } = useParams()
  const obra = useObra(obraId)
  const tree = useChecklist(obraId)

  const toggle = useToggleItem(obraId)
  const criarItem = useCriarItem(obraId)
  const excluirEtapa = useExcluirEtapa(obraId)
  const excluirItem = useExcluirItem(obraId)

  const [criandoEtapa, setCriandoEtapa] = useState(false)
  const [importando, setImportando] = useState(false)
  const [pending, setPending] = useState<PendingDelete>(null)

  function onToggle(item: Item, estado: EstadoItem) {
    toggle.mutate(
      { item, estado },
      { onError: () => toast.error("Não consegui atualizar — o estado pode ter mudado no servidor.") },
    )
  }

  async function onAddItem(etapaId: string, nome: string) {
    try {
      await criarItem.mutateAsync({ etapa_id: etapaId, nome })
    } catch {
      toast.error("Não foi possível adicionar o item.")
    }
  }

  async function onConfirmDelete() {
    if (!pending) return
    try {
      if (pending.kind === "etapa") await excluirEtapa.mutateAsync(pending.id)
      else await excluirItem.mutateAsync(pending.id)
      toast.success(pending.kind === "etapa" ? "Etapa excluída" : "Item excluído")
      setPending(null)
    } catch {
      toast.error("Não foi possível excluir.")
    }
  }

  const etapas = tree.data?.etapas ?? []

  return (
    <div className="animate-fade-up">
      <Link
        to="/"
        className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronLeft className="size-4" />
        Obras
      </Link>

      <div className="mb-6 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.3em] text-primary">
            Obra #{obra.data?.seq_humano ?? "—"}
          </div>
          <h1 className="truncate font-word text-3xl leading-tight">
            {obra.data?.nome ?? "…"}
          </h1>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button variant="outline" size="icon" title="Importar" onClick={() => setImportando(true)}>
            <Upload />
          </Button>
          <Button onClick={() => setCriandoEtapa(true)}>
            <Plus />
            Etapa
          </Button>
        </div>
      </div>

      {tree.isLoading && <CenteredSpinner />}
      {tree.isError && (
        <ErrorState message="Não foi possível carregar o checklist." onRetry={() => void tree.refetch()} />
      )}

      {tree.isSuccess && etapas.length === 0 && (
        <EmptyState
          icon={ListChecks}
          title="Checklist vazio"
          description="Importe um template .xlsx ou crie a primeira etapa manualmente."
          action={
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setImportando(true)}>
                <Upload />
                Importar
              </Button>
              <Button onClick={() => setCriandoEtapa(true)}>
                <Plus />
                Nova etapa
              </Button>
            </div>
          }
        />
      )}

      {tree.isSuccess && etapas.length > 0 && (
        <div className="space-y-4">
          {etapas.map((etapa) => (
            <EtapaCard
              key={etapa.id}
              etapa={etapa}
              onToggle={onToggle}
              onAddItem={onAddItem}
              onDeleteEtapa={(e) =>
                setPending({ kind: "etapa", id: e.id, label: e.nome, count: e.itens.length })
              }
              onDeleteItem={(i) => setPending({ kind: "item", id: i.id, label: i.nome })}
            />
          ))}
        </div>
      )}

      <CriarEtapaDialog obraId={obraId} open={criandoEtapa} onOpenChange={setCriandoEtapa} />
      <ImportarChecklistDialog obraId={obraId} open={importando} onOpenChange={setImportando} />
      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(o) => !o && setPending(null)}
        title={pending?.kind === "etapa" ? "Excluir etapa?" : "Excluir item?"}
        description={
          pending?.kind === "etapa" ? (
            <>
              "{pending.label}" e seus <strong>{pending.count}</strong> item(ns) serão removidos.
              Esta ação não pode ser desfeita.
            </>
          ) : (
            <>"{pending?.label}" será removido.</>
          )
        }
        pending={excluirEtapa.isPending || excluirItem.isPending}
        onConfirm={onConfirmDelete}
      />
    </div>
  )
}

function EtapaCard({
  etapa,
  onToggle,
  onAddItem,
  onDeleteEtapa,
  onDeleteItem,
}: {
  etapa: Etapa
  onToggle: (item: Item, estado: EstadoItem) => void
  onAddItem: (etapaId: string, nome: string) => Promise<void>
  onDeleteEtapa: (etapa: Etapa) => void
  onDeleteItem: (item: Item) => void
}) {
  const feitos = etapa.itens.filter((i) => i.estado === "concluido").length
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-border p-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-display text-xs text-muted-foreground">#{etapa.seq_humano ?? "—"}</span>
            {etapa.itens.length > 0 && (
              <span className="text-[11px] text-muted-foreground">
                {feitos}/{etapa.itens.length} feitos
              </span>
            )}
          </div>
          <h2 className="truncate text-base font-medium">{etapa.nome}</h2>
        </div>
        <button
          type="button"
          onClick={() => onDeleteEtapa(etapa)}
          aria-label="Excluir etapa"
          title="Excluir etapa"
          className="shrink-0 rounded-lg p-2 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
        >
          <Trash2 className="size-4" />
        </button>
      </div>

      <ul className="divide-y divide-border">
        {etapa.itens.map((item) => (
          <li key={item.id} className="flex items-center gap-3 px-4 py-3">
            <StateToggle value={item.estado} onChange={(e) => onToggle(item, e)} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm">{item.nome}</p>
              {item.estado === "concluido" && item.concluido_por_nome && (
                <p className="truncate text-[11px] text-muted-foreground">
                  por {item.concluido_por_nome}
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => onDeleteItem(item)}
              aria-label="Excluir item"
              title="Excluir item"
              className="shrink-0 rounded-lg p-2 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
            >
              <Trash2 className="size-4" />
            </button>
          </li>
        ))}
      </ul>

      <AddItemInline etapaId={etapa.id} onAdd={onAddItem} />
    </Card>
  )
}

function AddItemInline({
  etapaId,
  onAdd,
}: {
  etapaId: string
  onAdd: (etapaId: string, nome: string) => Promise<void>
}) {
  const [nome, setNome] = useState("")
  const [salvando, setSalvando] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    const v = nome.trim()
    if (!v || salvando) return
    setSalvando(true)
    await onAdd(etapaId, v)
    setNome("")
    setSalvando(false)
  }

  return (
    <form onSubmit={submit} className="flex items-center gap-2 border-t border-border p-3">
      <Input
        value={nome}
        onChange={(e) => setNome(e.target.value)}
        maxLength={300}
        placeholder="Adicionar item…"
        className="h-9 border-0 bg-transparent px-1 focus-visible:ring-0"
      />
      <Button type="submit" size="sm" variant="ghost" disabled={!nome.trim() || salvando}>
        <Plus />
        Item
      </Button>
    </form>
  )
}
