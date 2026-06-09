import {
  CalendarRange,
  Camera,
  ChartGantt,
  CheckCircle2,
  ChevronLeft,
  Circle,
  ListChecks,
  Loader2,
  Pencil,
  Plus,
  Printer,
  Trash2,
  Upload,
} from "lucide-react"
import { useState, type FormEvent } from "react"
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"

import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Input } from "@/components/ui/input"
import { FotosDialog, type FotosTarget } from "@/features/anexos/FotosDialog"
import { ApiError, api } from "@/lib/api"
import {
  useChecklist,
  useCriarItem,
  useExcluirEtapa,
  useExcluirItem,
  useSetEtapaConcluida,
  useToggleItem,
  type EstadoItem,
  type Etapa,
  type Item,
} from "@/features/checklist/checklistApi"
import { CriarEtapaDialog } from "@/features/checklist/CriarEtapaDialog"
import { formatIntervalo } from "@/features/checklist/cronograma"
import { hojeISO, montarGantt } from "@/features/checklist/gantt"
import { CronogramaMacroDialog } from "@/features/checklist/CronogramaMacroDialog"
import { EtapaDatasDialog } from "@/features/checklist/EtapaDatasDialog"
import { ImportarChecklistDialog } from "@/features/checklist/ImportarChecklistDialog"
import { ItemDetalhesDialog } from "@/features/checklist/ItemDetalhesDialog"
import { StateToggle } from "@/features/checklist/StateToggle"
import { useObra } from "@/features/obras/obrasApi"
import { uuidv4 } from "@/lib/uuid"

type PendingDelete =
  | { kind: "etapa"; id: string; label: string; count: number }
  | { kind: "item"; id: string; label: string; count: number }
  | null

const brl = (n: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(n)
const numFmt = (n: number) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 }).format(n)

const subtotalEtapa = (etapa: Etapa) => etapa.itens.reduce((s, i) => s + (i.custo_total ?? 0), 0)

/** Agrupa itens por ambiente preservando a ordem de 1ª aparição (null = sem cômodo). */
function agruparPorAmbiente(itens: Item[]): { ambiente: string | null; itens: Item[] }[] {
  const grupos: { ambiente: string | null; itens: Item[] }[] = []
  const idx = new Map<string, number>()
  for (const it of itens) {
    const key = it.ambiente?.trim() || ""
    let g = idx.get(key)
    if (g === undefined) {
      g = grupos.length
      idx.set(key, g)
      grupos.push({ ambiente: key || null, itens: [] })
    }
    grupos[g].itens.push(it)
  }
  return grupos
}

export function CronogramaPage() {
  const { obraId = "" } = useParams()
  const obra = useObra(obraId)
  const tree = useChecklist(obraId)

  const toggle = useToggleItem(obraId)
  const criarItem = useCriarItem(obraId)
  const excluirEtapa = useExcluirEtapa(obraId)
  const excluirItem = useExcluirItem(obraId)
  const setEtapaConcluida = useSetEtapaConcluida(obraId)

  const [criandoEtapa, setCriandoEtapa] = useState(false)
  const [importando, setImportando] = useState(false)
  const [pending, setPending] = useState<PendingDelete>(null)
  const [fotos, setFotos] = useState<FotosTarget | null>(null)
  const [editando, setEditando] = useState<Item | null>(null)
  const [exportando, setExportando] = useState(false)
  const [macroAberto, setMacroAberto] = useState(false)
  const [etapaDatas, setEtapaDatas] = useState<Etapa | null>(null)

  const ehArquiteto = obra.data?.meu_papel === "arquiteto"

  async function exportarPdf() {
    if (exportando) return
    setExportando(true)
    try {
      const blob = await api.getBlob(`/api/v1/obras/${obraId}/checklist/pdf`)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `cronograma-${obra.data?.nome ?? "obra"}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 4000)
    } catch (err) {
      if (err instanceof ApiError && err.isUpgrade) {
        toast.error("Exportar em PDF é um recurso Pro.", {
          description: "Faça upgrade do plano para gerar o checklist em PDF.",
        })
      } else {
        toast.error("Não foi possível gerar o PDF.")
      }
    } finally {
      setExportando(false)
    }
  }

  function onToggle(item: Item, estado: EstadoItem) {
    toggle.mutate(
      { item, estado },
      { onError: () => toast.error("Não consegui atualizar — o estado pode ter mudado no servidor.") },
    )
  }

  function onToggleEtapaConcluida(etapa: Etapa) {
    setEtapaConcluida.mutate(
      { etapa, concluida: !etapa.concluida },
      { onError: () => toast.error("Não consegui atualizar a conclusão da etapa.") },
    )
  }

  async function onAddItem(etapaId: string, nome: string, parentId?: string) {
    try {
      await criarItem.mutateAsync({
        id: uuidv4(),
        etapa_id: etapaId,
        nome,
        parent_item_id: parentId,
      })
    } catch {
      toast.error("Não foi possível adicionar.")
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
  const orcamentoTotal = etapas.reduce((s, e) => s + subtotalEtapa(e), 0)
  // mostra o Gantt só quando há algo desenhável (mesma fonte que a tela do Gantt usa p/ montar).
  const temGantt = montarGantt(etapas, hojeISO()) !== null

  return (
    <div className="animate-fade-up">
      <Link
        to={`/obras/${obraId}`}
        className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronLeft className="size-4" />
        {obra.data?.nome ?? "Obra"}
      </Link>

      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.3em] text-primary">
            Obra #{obra.data?.seq_humano ?? "—"}
          </div>
          <h1 className="font-word text-3xl leading-tight">Cronograma</h1>
          {orcamentoTotal > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">
              Orçamento <span className="text-primary">{brl(orcamentoTotal)}</span>
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          {temGantt && (
            <Button asChild variant="outline" size="icon" title="Gráfico de Gantt">
              <Link to={`/obras/${obraId}/cronograma/gantt`}>
                <ChartGantt />
              </Link>
            </Button>
          )}
          {ehArquiteto && etapas.length > 0 && (
            <Button
              variant="outline"
              size="icon"
              title="Cronograma macro"
              onClick={() => setMacroAberto(true)}
            >
              <CalendarRange />
            </Button>
          )}
          {ehArquiteto && etapas.length > 0 && (
            <Button
              variant="outline"
              size="icon"
              title="Exportar PDF"
              onClick={exportarPdf}
              disabled={exportando}
            >
              {exportando ? <Loader2 className="animate-spin" /> : <Printer />}
            </Button>
          )}
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
          description="Importe sua planilha de orçamento (.xlsx) ou crie a primeira etapa manualmente."
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
              ehArquiteto={ehArquiteto}
              onToggle={onToggle}
              onToggleEtapaConcluida={onToggleEtapaConcluida}
              onAddItem={onAddItem}
              onFotos={setFotos}
              onEdit={setEditando}
              onEditEtapaDatas={setEtapaDatas}
              onDeleteEtapa={(e) =>
                setPending({ kind: "etapa", id: e.id, label: e.nome, count: e.itens.length })
              }
              onDeleteItem={(i) =>
                setPending({
                  kind: "item",
                  id: i.id,
                  label: i.nome,
                  count: i.subitens.length,
                })
              }
            />
          ))}
        </div>
      )}

      <CriarEtapaDialog obraId={obraId} open={criandoEtapa} onOpenChange={setCriandoEtapa} />
      <ImportarChecklistDialog obraId={obraId} open={importando} onOpenChange={setImportando} />
      <ItemDetalhesDialog
        obraId={obraId}
        item={editando}
        onOpenChange={(o) => !o && setEditando(null)}
      />
      <CronogramaMacroDialog
        obraId={obraId}
        obra={obra.data}
        etapas={etapas}
        open={macroAberto}
        onOpenChange={setMacroAberto}
      />
      <EtapaDatasDialog
        obraId={obraId}
        etapa={etapaDatas}
        onOpenChange={(o) => !o && setEtapaDatas(null)}
      />
      <FotosDialog obraId={obraId} target={fotos} onOpenChange={(o) => !o && setFotos(null)} />
      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(o) => !o && setPending(null)}
        title={pending?.kind === "etapa" ? "Excluir etapa?" : "Excluir tarefa?"}
        description={
          pending?.kind === "etapa" ? (
            <>
              "{pending.label}" e seus <strong>{pending.count}</strong> item(ns) serão removidos.
              Esta ação não pode ser desfeita.
            </>
          ) : pending && pending.count > 0 ? (
            <>
              "{pending.label}" e seus <strong>{pending.count}</strong> item(ns) de checklist serão
              removidos.
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
  ehArquiteto,
  onToggle,
  onToggleEtapaConcluida,
  onAddItem,
  onFotos,
  onEdit,
  onEditEtapaDatas,
  onDeleteEtapa,
  onDeleteItem,
}: {
  etapa: Etapa
  ehArquiteto: boolean
  onToggle: (item: Item, estado: EstadoItem) => void
  onToggleEtapaConcluida: (etapa: Etapa) => void
  onAddItem: (etapaId: string, nome: string, parentId?: string) => Promise<void>
  onFotos: (target: FotosTarget) => void
  onEdit: (item: Item) => void
  onEditEtapaDatas: (etapa: Etapa) => void
  onDeleteEtapa: (etapa: Etapa) => void
  onDeleteItem: (item: Item) => void
}) {
  const intervalo = formatIntervalo(etapa.data_inicio, etapa.data_fim)
  // unidades-folha da etapa: cada sub-item, ou a própria tarefa quando ela não tem sub-itens.
  const folhasEtapa = etapa.itens.flatMap((t) => (t.subitens.length > 0 ? t.subitens : [t]))
  const feitos = folhasEtapa.filter((s) => s.estado === "concluido").length
  const subtotal = subtotalEtapa(etapa)
  const grupos = agruparPorAmbiente(etapa.itens)
  const temAmbiente = grupos.some((g) => g.ambiente)
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-border p-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-display text-xs text-muted-foreground">#{etapa.seq_humano ?? "—"}</span>
            {folhasEtapa.length > 0 && (
              <span className="text-[11px] text-muted-foreground">
                {feitos}/{folhasEtapa.length} feitos
              </span>
            )}
            {subtotal > 0 && <span className="text-[11px] text-primary/80">{brl(subtotal)}</span>}
            {intervalo && (
              <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                <CalendarRange className="size-3" />
                {intervalo}
              </span>
            )}
            {etapa.sem_itens && etapa.concluida && (
              <span className="inline-flex items-center gap-1 text-[11px] text-primary">
                <CheckCircle2 className="size-3" />
                concluída
              </span>
            )}
          </div>
          <h2 className="text-base font-medium break-words">{etapa.nome}</h2>
        </div>
        <div className="flex shrink-0 items-center">
          {etapa.sem_itens && ehArquiteto && (
            <>
              <button
                type="button"
                onClick={() => onToggleEtapaConcluida(etapa)}
                aria-label={etapa.concluida ? "Marcar como não concluída" : "Marcar como concluída"}
                title={etapa.concluida ? "Concluída" : "Marcar como concluída"}
                className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-primary"
              >
                {etapa.concluida ? (
                  <CheckCircle2 className="size-4 text-primary" />
                ) : (
                  <Circle className="size-4" />
                )}
              </button>
              <button
                type="button"
                onClick={() => onEditEtapaDatas(etapa)}
                aria-label="Datas da etapa"
                title="Datas da etapa"
                className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-primary"
              >
                <CalendarRange className="size-4" />
              </button>
            </>
          )}
          <button
            type="button"
            onClick={() => onFotos({ parentType: "etapa", parentId: etapa.id, titulo: etapa.nome })}
            aria-label="Fotos da etapa"
            title="Fotos da etapa"
            className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-primary"
          >
            <Camera className="size-4" />
          </button>
          <button
            type="button"
            onClick={() => onDeleteEtapa(etapa)}
            aria-label="Excluir etapa"
            title="Excluir etapa"
            className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="size-4" />
          </button>
        </div>
      </div>

      <div>
        {grupos.map((g, gi) => (
          <div key={g.ambiente ?? `__sem_${gi}`}>
            {temAmbiente && (
              <div
                className={`bg-muted/30 px-4 py-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground${gi > 0 ? " border-t border-border" : ""}`}
              >
                {g.ambiente ?? "Geral"}
              </div>
            )}
            <div className="divide-y divide-border">
              {g.itens.map((tarefa) => (
                <TarefaBlock
                  key={tarefa.id}
                  tarefa={tarefa}
                  onToggle={onToggle}
                  onAddItem={onAddItem}
                  onFotos={onFotos}
                  onEdit={onEdit}
                  onDeleteItem={onDeleteItem}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-border px-4 py-1">
        <AddInline
          placeholder="Adicionar tarefa…"
          cta="Tarefa"
          onAdd={(nome) => onAddItem(etapa.id, nome)}
        />
      </div>
    </Card>
  )
}

function TarefaBlock({
  tarefa,
  onToggle,
  onAddItem,
  onFotos,
  onEdit,
  onDeleteItem,
}: {
  tarefa: Item
  onToggle: (item: Item, estado: EstadoItem) => void
  onAddItem: (etapaId: string, nome: string, parentId?: string) => Promise<void>
  onFotos: (target: FotosTarget) => void
  onEdit: (item: Item) => void
  onDeleteItem: (item: Item) => void
}) {
  const subs = tarefa.subitens
  const feitos = subs.filter((s) => s.estado === "concluido").length
  const completa = subs.length > 0 && feitos === subs.length
  return (
    <div className="px-2 py-2">
      {/* cabeçalho da tarefa: tarefa-FOLHA (sem sub-itens) ganha o toggle de 3 estados; com
          sub-itens mostra só o progresso (deriva dos filhos). */}
      <div className="flex items-start gap-2 px-2 py-1">
        {subs.length === 0 && (
          <StateToggle value={tarefa.estado} onChange={(e) => onToggle(tarefa, e)} />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{tarefa.nome}</p>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
            {subs.length > 0 && (
              <span className={completa ? "text-primary" : ""}>
                {feitos}/{subs.length} feitos
              </span>
            )}
            {tarefa.quantidade != null && (
              <span>
                {numFmt(tarefa.quantidade)}
                {tarefa.unidade ? ` ${tarefa.unidade}` : ""}
              </span>
            )}
            {tarefa.custo_total != null && (
              <span className="text-primary/80">{brl(tarefa.custo_total)}</span>
            )}
            {formatIntervalo(tarefa.data_inicio, tarefa.data_fim) && (
              <span className="inline-flex items-center gap-1">
                <CalendarRange className="size-3" />
                {formatIntervalo(tarefa.data_inicio, tarefa.data_fim)}
              </span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center">
          <button
            type="button"
            onClick={() => onEdit(tarefa)}
            aria-label="Cômodo / orçamento"
            title="Cômodo / orçamento"
            className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-primary"
          >
            <Pencil className="size-4" />
          </button>
          <button
            type="button"
            onClick={() =>
              onFotos({ parentType: "checklist_item", parentId: tarefa.id, titulo: tarefa.nome })
            }
            aria-label="Fotos da tarefa"
            title="Fotos da tarefa"
            className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-primary"
          >
            <Camera className="size-4" />
          </button>
          <button
            type="button"
            onClick={() => onDeleteItem(tarefa)}
            aria-label="Excluir tarefa"
            title="Excluir tarefa"
            className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
          >
            <Trash2 className="size-4" />
          </button>
        </div>
      </div>

      {/* sub-itens do checklist (filhos): aqui sim o toggle de 3 estados */}
      <div className="ml-3 border-l border-border pl-1">
        {subs.map((s) => (
          <div key={s.id} className="flex items-center gap-3 py-2 pl-2 pr-1">
            <StateToggle value={s.estado} onChange={(e) => onToggle(s, e)} />
            <div className="min-w-0 flex-1">
              <p className="break-words text-sm">{s.nome}</p>
              {s.estado === "concluido" && s.concluido_por_nome && (
                <p className="break-words text-[11px] text-muted-foreground">por {s.concluido_por_nome}</p>
              )}
            </div>
            <button
              type="button"
              onClick={() => onFotos({ parentType: "checklist_item", parentId: s.id, titulo: s.nome })}
              aria-label="Fotos do item"
              title="Fotos do item"
              className="shrink-0 rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-primary"
            >
              <Camera className="size-4" />
            </button>
            <button
              type="button"
              onClick={() => onDeleteItem(s)}
              aria-label="Excluir item"
              title="Excluir item"
              className="shrink-0 rounded-lg p-2 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
            >
              <Trash2 className="size-4" />
            </button>
          </div>
        ))}
        <AddInline
          placeholder="Adicionar item do checklist…"
          cta="Item"
          onAdd={(nome) => onAddItem(tarefa.etapa_id, nome, tarefa.id)}
        />
      </div>
    </div>
  )
}

function AddInline({
  placeholder,
  cta,
  onAdd,
}: {
  placeholder: string
  cta: string
  onAdd: (nome: string) => Promise<void>
}) {
  const [nome, setNome] = useState("")

  function submit(e: FormEvent) {
    e.preventDefault()
    const v = nome.trim()
    if (!v) return
    // UI otimista: limpa o campo JÁ no enter (não espera o servidor — na latência do mobile o texto
    // ficava lá). Não bloqueia o próximo item; onAdd já é otimista e trata o próprio erro (toast).
    setNome("")
    void Promise.resolve(onAdd(v)).catch(() => {})
  }

  return (
    <form onSubmit={submit} className="flex items-center gap-2 py-1">
      <Input
        value={nome}
        onChange={(e) => setNome(e.target.value)}
        maxLength={300}
        placeholder={placeholder}
        className="h-9 min-w-0 flex-1 border-0 bg-transparent px-1 text-sm focus-visible:ring-0"
      />
      <Button type="submit" size="sm" variant="ghost" className="shrink-0" disabled={!nome.trim()}>
        <Plus />
        {cta}
      </Button>
    </form>
  )
}
