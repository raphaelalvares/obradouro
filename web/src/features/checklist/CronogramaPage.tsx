import {
  CalendarClock,
  CalendarRange,
  Camera,
  ChartGantt,
  CheckCircle2,
  ChevronLeft,
  Circle,
  Coins,
  DoorOpen,
  Eraser,
  HelpCircle,
  Layers,
  Link2,
  ListChecks,
  Loader2,
  Lock,
  Pencil,
  Plus,
  Printer,
  Trash2,
  Upload,
  Users,
} from "lucide-react"
import { useState, type ComponentType, type FormEvent, type ReactNode } from "react"
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
  contagemEtapa,
  custoEtapa,
  custoItem,
  custoSubetapa,
  folhasDe,
  montarWbs,
  rotuloAguarda,
  tarefasDaEtapa,
  useChecklist,
  useCriarItem,
  useCriarSubetapa,
  useExcluirEtapa,
  useExcluirItem,
  useExcluirSubetapa,
  useLimparObra,
  useRecalcular,
  useRenomearEtapa,
  useRenomearSubetapa,
  useSetEtapaConcluida,
  useSetSubetapaConcluida,
  useToggleItem,
  type Ambiente,
  type CustoForm,
  type EstadoItem,
  type Etapa,
  type Item,
  type SubetapaTree,
  type WbsMaps,
} from "@/features/checklist/checklistApi"
import { AmbientesDialog } from "@/features/checklist/AmbientesDialog"
import { EquipesDialog } from "@/features/equipes/EquipesDialog"
import { useEquipes, type Equipe } from "@/features/equipes/equipesApi"
import { CriarEtapaDialog } from "@/features/checklist/CriarEtapaDialog"
import { CriarTarefaDialog, type NovaTarefaTarget } from "@/features/checklist/CriarTarefaDialog"
import { NodeDetalhesDialog, type NodeCustoTarget } from "@/features/checklist/NodeDetalhesDialog"
import { DependenciasDialog } from "@/features/checklist/DependenciasDialog"
import { duracaoLabel, formatIntervalo } from "@/features/checklist/cronograma"
import { hojeISO, montarGantt } from "@/features/checklist/gantt"
import { CronogramaMacroDialog } from "@/features/checklist/CronogramaMacroDialog"
import { EtapaDatasDialog } from "@/features/checklist/EtapaDatasDialog"
import { SubetapaDatasDialog } from "@/features/checklist/SubetapaDatasDialog"
import { ImportarChecklistDialog } from "@/features/checklist/ImportarChecklistDialog"
import { ItemDetalhesDialog } from "@/features/checklist/ItemDetalhesDialog"
import { StateToggle } from "@/features/checklist/StateToggle"
import { useObra } from "@/features/obras/obrasApi"
import { uuidv4 } from "@/lib/uuid"

type PendingDelete =
  | { kind: "etapa"; id: string; label: string; count: number }
  | { kind: "subetapa"; id: string; label: string; count: number }
  | { kind: "item"; id: string; label: string; count: number }
  | null

/** Opções de criação de tarefa: sob uma subetapa (subetapaId) ou como sub-item de uma tarefa (parentId). */
type AddOpts = { parentId?: string; subetapaId?: string }

const brl = (n: number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(n)
const numFmt = (n: number) => new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 }).format(n)

/** Hint curto da composição de custo de uma FOLHA (etapa/subetapa/tarefa) p/ bater o olho ao lado do
 * valor: "500 m² · mat R$ 200 + M.O. R$ 40/un" ou "verba". Null quando não há o que compor. */
function composicaoCusto(n: {
  unidade: string | null
  quantidade: number | null
  valor_unitario: number | null
  mao_obra_unitaria: number | null
}): string | null {
  const un = n.unidade?.trim() || null
  if (un != null && /^(vb|verba)$/i.test(un)) return "verba"
  const partes: string[] = []
  if (n.quantidade != null) partes.push(`${numFmt(n.quantidade)}${un ? ` ${un}` : ""}`)
  const precos: string[] = []
  if (n.valor_unitario != null) precos.push(`mat ${brl(n.valor_unitario)}`)
  if (n.mao_obra_unitaria != null) precos.push(`M.O. ${brl(n.mao_obra_unitaria)}`)
  if (precos.length) partes.push(`${precos.join(" + ")}/un`)
  return partes.length ? partes.join(" · ") : null
}

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
  const equipesQ = useEquipes()

  const toggle = useToggleItem(obraId)
  const criarItem = useCriarItem(obraId)
  const criarSubetapa = useCriarSubetapa(obraId)
  const excluirEtapa = useExcluirEtapa(obraId)
  const excluirSubetapa = useExcluirSubetapa(obraId)
  const excluirItem = useExcluirItem(obraId)
  const limparObra = useLimparObra(obraId)
  const setEtapaConcluida = useSetEtapaConcluida(obraId)
  const setSubetapaConcluida = useSetSubetapaConcluida(obraId)
  const recalcular = useRecalcular(obraId)
  const renomearEtapa = useRenomearEtapa(obraId)
  const renomearSubetapa = useRenomearSubetapa(obraId)

  async function onRenameEtapa(etapaId: string, nome: string) {
    try {
      await renomearEtapa.mutateAsync({ etapaId, nome })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível renomear.")
    }
  }
  async function onRenameSubetapa(subetapaId: string, nome: string) {
    try {
      await renomearSubetapa.mutateAsync({ subetapaId, nome })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível renomear.")
    }
  }

  const [criandoEtapa, setCriandoEtapa] = useState(false)
  const [importando, setImportando] = useState(false)
  const [pending, setPending] = useState<PendingDelete>(null)
  const [limpando, setLimpando] = useState(false)
  const [fotos, setFotos] = useState<FotosTarget | null>(null)
  const [editando, setEditando] = useState<Item | null>(null)
  const [depTarefa, setDepTarefa] = useState<Item | null>(null)
  const [exportando, setExportando] = useState(false)
  const [macroAberto, setMacroAberto] = useState(false)
  const [etapaDatas, setEtapaDatas] = useState<Etapa | null>(null)
  const [subetapaDatas, setSubetapaDatas] = useState<SubetapaTree | null>(null)
  const [ambientesAberto, setAmbientesAberto] = useState(false)
  const [equipesAberto, setEquipesAberto] = useState(false)
  const [vista, setVista] = useState<"etapa" | "ambiente">("etapa")
  const [ajudaAberta, setAjudaAberta] = useState(false)
  const [criarTarefa, setCriarTarefa] = useState<NovaTarefaTarget | null>(null)
  const [nodeCusto, setNodeCusto] = useState<NodeCustoTarget | null>(null)
  // confirma o "empurrar custo pra baixo" ANTES de criar o 1º filho de um nó custeado.
  const [moveConfirm, setMoveConfirm] = useState<{
    tipo: "item" | "subetapa"
    etapaId: string
    nome: string
    opts?: AddOpts
    paiLabel: string
    valor: number
  } | null>(null)

  const ehArquiteto = obra.data?.meu_papel === "arquiteto"
  const equipes = equipesQ.data ?? []
  const equipesMap = new Map(equipes.map((e) => [e.id, e] as const))

  async function exportarPdf() {
    if (exportando) return
    setExportando(true)
    try {
      const blob = await api.getBlob(`/api/v1/obras/${obraId}/checklist/pdf`)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `cronograma-${(obra.data?.nome ?? "obra").replace(/[\\/:*?"<>|]+/g, "_")}.pdf`
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
      {
        onError: (err) =>
          toast.error(
            err instanceof ApiError
              ? err.message // ex.: "tarefa bloqueada por dependência (aguarda #3)"
              : "Não consegui atualizar — o estado pode ter mudado no servidor.",
          ),
      },
    )
  }

  async function onRecalcular() {
    if (recalcular.isPending) return
    try {
      await recalcular.mutateAsync({})
      toast.success("Datas recalculadas pela rede de dependências.")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível recalcular.")
    }
  }

  function onToggleEtapaConcluida(etapa: Etapa) {
    setEtapaConcluida.mutate(
      { etapa, concluida: !etapa.concluida },
      { onError: () => toast.error("Não consegui atualizar a conclusão da etapa.") },
    )
  }

  function onToggleSubetapaConcluida(subetapa: SubetapaTree) {
    setSubetapaConcluida.mutate(
      { subetapa, concluida: !subetapa.concluida },
      { onError: () => toast.error("Não consegui atualizar a conclusão da subetapa.") },
    )
  }

  /** O nó-PAI que vai ganhar este filho é uma folha-com-custo? (etapa vazia, subetapa vazia, ou
   * tarefa-folha — todas com custo > 0). Se sim, criar o 1º filho empurra o custo pra baixo. */
  function paiCusteado(etapaId: string, opts?: AddOpts): { valor: number; label: string } | null {
    const etapa = etapas.find((e) => e.id === etapaId)
    if (!etapa) return null
    if (opts?.parentId) {
      const tarefa = [...etapa.itens, ...etapa.subetapas.flatMap((s) => s.itens)].find(
        (t) => t.id === opts.parentId,
      )
      return tarefa && tarefa.subitens.length === 0 && (tarefa.custo_total ?? 0) > 0
        ? { valor: tarefa.custo_total ?? 0, label: tarefa.nome }
        : null
    }
    if (opts?.subetapaId) {
      const se = etapa.subetapas.find((s) => s.id === opts.subetapaId)
      return se && se.itens.length === 0 && (se.custo_total ?? 0) > 0
        ? { valor: se.custo_total ?? 0, label: se.nome }
        : null
    }
    return etapa.subetapas.length === 0 && etapa.itens.length === 0 && (etapa.custo_total ?? 0) > 0
      ? { valor: etapa.custo_total ?? 0, label: etapa.nome }
      : null
  }

  async function criarItemDireto(etapaId: string, nome: string, opts?: AddOpts, custo?: CustoForm) {
    await criarItem.mutateAsync({
      id: uuidv4(),
      etapa_id: etapaId,
      nome,
      parent_item_id: opts?.parentId,
      subetapa_id: opts?.subetapaId,
      ...(custo ?? {}),
    })
  }

  async function onAddItem(etapaId: string, nome: string, opts?: AddOpts) {
    const pai = paiCusteado(etapaId, opts)
    if (pai) {
      setMoveConfirm({ tipo: "item", etapaId, nome, opts, paiLabel: pai.label, valor: pai.valor })
      return
    }
    try {
      await criarItemDireto(etapaId, nome, opts)
    } catch {
      toast.error("Não foi possível adicionar.")
    }
  }

  async function onAddSubetapa(etapaId: string, nome: string) {
    const pai = paiCusteado(etapaId)
    if (pai) {
      setMoveConfirm({ tipo: "subetapa", etapaId, nome, paiLabel: pai.label, valor: pai.valor })
      return
    }
    try {
      await criarSubetapa.mutateAsync({ id: uuidv4(), etapa_id: etapaId, nome })
    } catch {
      toast.error("Não foi possível adicionar a subetapa.")
    }
  }

  /** Confirmado o move-down: cria o filho (sem custo próprio); o backend desce o custo do pai. */
  async function onConfirmMove() {
    if (!moveConfirm) return
    const m = moveConfirm
    try {
      if (m.tipo === "subetapa") {
        await criarSubetapa.mutateAsync({ id: uuidv4(), etapa_id: m.etapaId, nome: m.nome })
      } else {
        await criarItemDireto(m.etapaId, m.nome, m.opts)
      }
      setMoveConfirm(null)
    } catch {
      toast.error("Não foi possível adicionar.")
    }
  }

  /** Cria tarefa COM custo (via diálogo). Só ofertado quando o pai NÃO é folha-com-custo (sem
   * move-down possível), então cria direto. */
  async function onCriarTarefaComCusto(nome: string, custo: CustoForm) {
    if (!criarTarefa) return
    await criarItemDireto(criarTarefa.etapaId, nome, { subetapaId: criarTarefa.subetapaId }, custo)
  }

  async function onConfirmDelete() {
    if (!pending) return
    try {
      if (pending.kind === "etapa") await excluirEtapa.mutateAsync(pending.id)
      else if (pending.kind === "subetapa") await excluirSubetapa.mutateAsync(pending.id)
      else await excluirItem.mutateAsync(pending.id)
      toast.success(
        pending.kind === "etapa"
          ? "Etapa excluída"
          : pending.kind === "subetapa"
            ? "Subetapa excluída"
            : "Item excluído",
      )
      setPending(null)
    } catch {
      toast.error("Não foi possível excluir.")
    }
  }

  async function onConfirmLimpar() {
    if (limparObra.isPending) return
    try {
      const res = await limparObra.mutateAsync()
      toast.success(`Obra limpa — ${res.etapas_removidas} etapa(s) removida(s)`)
      setLimpando(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível limpar a obra.")
    }
  }

  const etapas = tree.data?.etapas ?? []
  // numeração hierárquica (EAP): 1 › 1.1 › 1.1.1 — posicional, reinicia por obra (mata o "#44").
  const wbs = montarWbs(etapas)
  const dependencias = tree.data?.dependencias ?? []
  const ambientes = tree.data?.ambientes ?? []
  const orcamentoTotal = etapas.reduce((s, e) => s + custoEtapa(e), 0)
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
          {ehArquiteto && dependencias.length > 0 && (
            <Button
              variant="outline"
              size="icon"
              title="Recalcular datas pelas dependências"
              onClick={onRecalcular}
              disabled={recalcular.isPending}
            >
              {recalcular.isPending ? <Loader2 className="animate-spin" /> : <CalendarClock />}
            </Button>
          )}
          {ehArquiteto && etapas.length > 0 && (
            <Button
              variant="outline"
              size="icon"
              title="Gerenciar cômodos"
              onClick={() => setAmbientesAberto(true)}
            >
              <DoorOpen />
            </Button>
          )}
          {ehArquiteto && (
            <Button
              variant="outline"
              size="icon"
              title="Gerenciar equipes"
              onClick={() => setEquipesAberto(true)}
            >
              <Users />
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
          <Button
            variant="outline"
            size="icon"
            title="Como funciona a EAP (4 níveis)"
            onClick={() => setAjudaAberta((v) => !v)}
          >
            <HelpCircle />
          </Button>
          <Button variant="outline" size="icon" title="Importar" onClick={() => setImportando(true)}>
            <Upload />
          </Button>
          <Button onClick={() => setCriandoEtapa(true)}>
            <Plus />
            Etapa
          </Button>
        </div>
      </div>

      {ajudaAberta && (
        <Card className="mb-4 border-primary/30 bg-primary/5 p-4 text-sm">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-medium">Como a EAP se organiza — 4 níveis</span>
            <button
              type="button"
              onClick={() => setAjudaAberta(false)}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              fechar
            </button>
          </div>
          <ul className="space-y-1 text-muted-foreground">
            <li>
              <span className="font-medium text-foreground">Etapa (1)</span> — a grande fase da obra.
            </li>
            <li>
              <span className="font-medium text-foreground">Subetapa (1.1)</span> — agrupa tarefas
              dentro da etapa. <em>Opcional.</em>
            </li>
            <li>
              <span className="font-medium text-foreground">Tarefa (1.1.2)</span> — o trabalho que se
              marca como feito, com custo, datas e responsável.
            </li>
            <li>
              <span className="font-medium text-foreground">SubTarefa (1.1.2.3)</span> — subdivide
              uma tarefa em passos.
            </li>
          </ul>
          <p className="mt-2 text-xs text-muted-foreground">
            A data e o custo de Etapa/Subetapa são <strong>calculados</strong> das tarefas abaixo
            (início = a 1ª começa · fim = a última termina). Uma etapa/subetapa <strong>vazia</strong>{" "}
            vira um <strong>marco</strong>, que você marca como concluído diretamente.
          </p>
        </Card>
      )}

      {tree.isLoading && <CenteredSpinner />}
      {tree.isError && (
        <ErrorState message="Não foi possível carregar o checklist." onRetry={() => void tree.refetch()} />
      )}

      {tree.isSuccess && etapas.length === 0 && (
        <EmptyState
          icon={ListChecks}
          title="Monte a EAP da obra"
          description="Organize a obra em 4 níveis — Etapa › Subetapa (opcional) › Tarefa › SubTarefa. Importe sua planilha de orçamento (.xlsx) ou crie a primeira etapa manualmente."
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
        <>
          {/* topo da lista: alternância de leitura (esq.) + ação destrutiva com trava (dir.) */}
          <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
            <div className="inline-flex rounded-lg border border-border p-0.5 text-sm">
              {(["etapa", "ambiente"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setVista(v)}
                  className={`rounded-md px-3 py-1 font-medium transition-colors ${
                    vista === v ? "bg-primary text-primary-foreground" : "text-muted-foreground"
                  }`}
                >
                  {v === "etapa" ? "Por etapa" : "Por cômodo"}
                </button>
              ))}
            </div>
            {ehArquiteto && (
              <div className="flex flex-col items-end gap-1">
                <Button
                  variant="outline"
                  size="sm"
                  className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                  onClick={() => setLimpando(true)}
                >
                  <Eraser />
                  Limpar obra
                </Button>
                <p className="max-w-[15rem] text-right text-[11px] leading-tight text-muted-foreground">
                  Apaga todas as etapas e tarefas. Trava: confirma e só libera o OK após 5&nbsp;s.
                </p>
              </div>
            )}
          </div>

          {vista === "etapa" ? (
            <div className="space-y-4">
              {etapas.map((etapa) => (
                <EtapaCard
                  key={etapa.id}
                  etapa={etapa}
                  wbs={wbs}
                  ehArquiteto={ehArquiteto}
                  equipesMap={equipesMap}
                  onToggle={onToggle}
                  onToggleEtapaConcluida={onToggleEtapaConcluida}
                  onToggleSubetapaConcluida={onToggleSubetapaConcluida}
                  onAddItem={onAddItem}
                  onAddSubetapa={onAddSubetapa}
                  onNovaTarefa={setCriarTarefa}
                  onEditarCusto={setNodeCusto}
                  onFotos={setFotos}
                  onEdit={setEditando}
                  onDeps={setDepTarefa}
                  onRenameEtapa={onRenameEtapa}
                  onRenameSubetapa={onRenameSubetapa}
                  onEditEtapaDatas={setEtapaDatas}
                  onEditSubetapaDatas={setSubetapaDatas}
                  onDeleteEtapa={(e) =>
                    setPending({
                      kind: "etapa",
                      id: e.id,
                      label: e.nome,
                      count: tarefasDaEtapa(e).length,
                    })
                  }
                  onDeleteSubetapa={(s) =>
                    setPending({ kind: "subetapa", id: s.id, label: s.nome, count: s.itens.length })
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
          ) : (
            <VistaAmbientes etapas={etapas} ambientes={ambientes} onToggle={onToggle} onFotos={setFotos} />
          )}
        </>
      )}

      <CriarEtapaDialog obraId={obraId} open={criandoEtapa} onOpenChange={setCriandoEtapa} />
      <ImportarChecklistDialog obraId={obraId} open={importando} onOpenChange={setImportando} />
      <ItemDetalhesDialog
        obraId={obraId}
        item={editando}
        ambientes={ambientes.map((a) => a.nome)}
        equipes={equipes}
        onOpenChange={(o) => !o && setEditando(null)}
      />
      <AmbientesDialog
        obraId={obraId}
        ambientes={ambientes}
        open={ambientesAberto}
        onOpenChange={setAmbientesAberto}
      />
      <EquipesDialog open={equipesAberto} onOpenChange={setEquipesAberto} />
      <DependenciasDialog
        obraId={obraId}
        tarefa={depTarefa}
        etapas={etapas}
        dependencias={dependencias}
        onOpenChange={(o) => !o && setDepTarefa(null)}
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
      <SubetapaDatasDialog
        obraId={obraId}
        subetapa={subetapaDatas}
        onOpenChange={(o) => !o && setSubetapaDatas(null)}
      />
      <FotosDialog obraId={obraId} target={fotos} onOpenChange={(o) => !o && setFotos(null)} />
      <CriarTarefaDialog
        target={criarTarefa}
        onOpenChange={(o) => !o && setCriarTarefa(null)}
        onCriar={onCriarTarefaComCusto}
      />
      <NodeDetalhesDialog
        obraId={obraId}
        target={nodeCusto}
        onOpenChange={(o) => !o && setNodeCusto(null)}
      />
      <ConfirmDialog
        open={moveConfirm !== null}
        onOpenChange={(o) => !o && setMoveConfirm(null)}
        variant="default"
        title="Mover o custo para baixo?"
        description={
          moveConfirm ? (
            <>
              "{moveConfirm.paiLabel}" tem <strong>{brl(moveConfirm.valor)}</strong> de custo. Como o
              custo fica sempre na folha mais baixa, ao criar "{moveConfirm.nome}" esse valor{" "}
              <strong>desce para o novo item</strong> e "{moveConfirm.paiLabel}" passa a só somar os
              filhos.
            </>
          ) : null
        }
        confirmLabel="Criar e mover"
        pending={criarItem.isPending || criarSubetapa.isPending}
        onConfirm={onConfirmMove}
      />
      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(o) => !o && setPending(null)}
        title={
          pending?.kind === "etapa"
            ? "Excluir etapa?"
            : pending?.kind === "subetapa"
              ? "Excluir subetapa?"
              : "Excluir tarefa?"
        }
        description={
          pending?.kind === "etapa" ? (
            <>
              "{pending.label}" e suas <strong>{pending.count}</strong> tarefa(s) serão removidas.
              Esta ação não pode ser desfeita.
            </>
          ) : pending?.kind === "subetapa" ? (
            <>
              "{pending.label}" e suas <strong>{pending.count}</strong> tarefa(s) serão removidas.
              Esta ação não pode ser desfeita.
            </>
          ) : pending && pending.count > 0 ? (
            <>
              "{pending.label}" e suas <strong>{pending.count}</strong> subtarefa(s) serão removidas.
            </>
          ) : (
            <>"{pending?.label}" será removido.</>
          )
        }
        pending={excluirEtapa.isPending || excluirSubetapa.isPending || excluirItem.isPending}
        onConfirm={onConfirmDelete}
      />
      <ConfirmDialog
        open={limpando}
        onOpenChange={(o) => !o && setLimpando(false)}
        title="Limpar toda a obra?"
        description={
          <>
            Isto remove <strong>todas as {etapas.length} etapa(s)</strong> e suas tarefas — junto vão
            as medições de avanço e as fotos das tarefas. <strong>Não dá para desfazer.</strong>
          </>
        }
        confirmLabel="Limpar obra"
        lockSeconds={5}
        pending={limparObra.isPending}
        onConfirm={onConfirmLimpar}
      />
    </div>
  )
}

/** Galho da árvore: linha-guia vertical + indentação. Aninhar <Rail> empilha as linhas (│ │ …),
 * deixando claro a que nível cada filho pertence (etapa › subetapa › tarefa › subtarefa). A borda
 * clareia conforme aprofunda (depth 1→3) p/ reforçar visualmente a profundidade. */
function Rail({ children, depth = 1 }: { children: ReactNode; depth?: number }) {
  const tom = depth >= 3 ? "border-border/40" : depth === 2 ? "border-border/70" : "border-border"
  return <div className={`border-l ${tom} pl-2 sm:pl-3`}>{children}</div>
}

/** Nome de um nó (etapa/subetapa) editável no lugar: clica → vira input; Enter/blur salva, Esc
 * cancela. Só p/ arquiteto (senão renderiza o texto puro). Fora de modal → autoFocus é OK
 * (a regra de "sem autoFocus" vale só p/ inputs dentro de Dialog/sheet). */
function NomeInline({
  nome,
  podeEditar,
  onRename,
}: {
  nome: string
  podeEditar: boolean
  onRename: (nome: string) => Promise<void>
}) {
  const [editando, setEditando] = useState(false)
  const [valor, setValor] = useState(nome)

  if (!podeEditar) return <>{nome}</>

  if (!editando) {
    return (
      <button
        type="button"
        title="Renomear"
        onClick={() => {
          setValor(nome)
          setEditando(true)
        }}
        className="text-left hover:underline hover:decoration-dotted hover:underline-offset-4"
      >
        {nome}
      </button>
    )
  }

  const salvar = async () => {
    const t = valor.trim()
    setEditando(false)
    if (t && t !== nome) await onRename(t)
  }

  return (
    <input
      autoFocus
      value={valor}
      maxLength={200}
      onChange={(e) => setValor(e.target.value)}
      onBlur={() => void salvar()}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault()
          void salvar()
        } else if (e.key === "Escape") {
          setValor(nome)
          setEditando(false)
        }
      }}
      style={{ font: "inherit" }}
      className="w-full min-w-0 rounded border border-input bg-background px-1 py-0 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    />
  )
}

function EtapaCard({
  etapa,
  wbs,
  ehArquiteto,
  equipesMap,
  onToggle,
  onToggleEtapaConcluida,
  onToggleSubetapaConcluida,
  onAddItem,
  onAddSubetapa,
  onNovaTarefa,
  onEditarCusto,
  onFotos,
  onEdit,
  onDeps,
  onRenameEtapa,
  onRenameSubetapa,
  onEditEtapaDatas,
  onEditSubetapaDatas,
  onDeleteEtapa,
  onDeleteSubetapa,
  onDeleteItem,
}: {
  etapa: Etapa
  wbs: WbsMaps
  ehArquiteto: boolean
  equipesMap: Map<string, Equipe>
  onToggle: (item: Item, estado: EstadoItem) => void
  onToggleEtapaConcluida: (etapa: Etapa) => void
  onToggleSubetapaConcluida: (subetapa: SubetapaTree) => void
  onAddItem: (etapaId: string, nome: string, opts?: AddOpts) => Promise<void>
  onAddSubetapa: (etapaId: string, nome: string) => Promise<void>
  onNovaTarefa: (target: NovaTarefaTarget) => void
  onEditarCusto: (target: NodeCustoTarget) => void
  onFotos: (target: FotosTarget) => void
  onEdit: (item: Item) => void
  onDeps: (item: Item) => void
  onRenameEtapa: (etapaId: string, nome: string) => Promise<void>
  onRenameSubetapa: (subetapaId: string, nome: string) => Promise<void>
  onEditEtapaDatas: (etapa: Etapa) => void
  onEditSubetapaDatas: (subetapa: SubetapaTree) => void
  onDeleteEtapa: (etapa: Etapa) => void
  onDeleteSubetapa: (subetapa: SubetapaTree) => void
  onDeleteItem: (item: Item) => void
}) {
  const intervalo = formatIntervalo(etapa.data_inicio, etapa.data_fim)
  const codigo = wbs.codigo.get(etapa.id) ?? "—"
  // duração/derivação só valem quando a etapa AGREGA (tem filhos); marco usa as datas próprias.
  const dur = etapa.sem_itens ? "" : duracaoLabel(etapa.data_inicio, etapa.data_fim)
  // unidades concluíveis da etapa: folhas (diretas + de subetapas) + cada subetapa-marco (1 cada).
  const cont = contagemEtapa(etapa)
  const subtotal = custoEtapa(etapa)
  // etapa-FOLHA com custo: adicionar filho move o custo pra baixo → some o botão "tarefa com custo".
  const custeadaFolha = etapa.sem_itens && (etapa.custo_total ?? 0) > 0
  const comp = custeadaFolha ? composicaoCusto(etapa) : null // hint de composição (só na folha)
  const grupos = agruparPorAmbiente(etapa.itens) // só as tarefas DIRETAS na etapa
  const temAmbiente = grupos.some((g) => g.ambiente)
  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between gap-2 border-b border-border p-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span className="rounded bg-muted px-1.5 py-0.5 font-display text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Etapa {codigo}
            </span>
            {etapa.sem_itens && (
              <span
                className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary"
                title="Etapa sem tarefas: marque como concluída direto. Ao adicionar tarefas, ela passa a somar o progresso delas."
              >
                Marco
              </span>
            )}
            {cont.total > 0 && (
              <span className="text-[11px] text-muted-foreground">
                {cont.feitos}/{cont.total} feitos
              </span>
            )}
            {subtotal > 0 && <span className="text-[11px] text-primary/80">{brl(subtotal)}</span>}
            {comp && <span className="text-[11px] text-muted-foreground">{comp}</span>}
            {intervalo && (
              <span
                className="inline-flex items-center gap-1 text-[11px] text-muted-foreground"
                title={
                  etapa.sem_itens
                    ? undefined
                    : "Calculado das tarefas: início = a 1ª começa · fim = a última termina"
                }
              >
                <CalendarRange className="size-3" />
                {intervalo}
                {dur && <span className="text-muted-foreground/70">· {dur}</span>}
              </span>
            )}
            {etapa.sem_itens && etapa.concluida && (
              <span className="inline-flex items-center gap-1 text-[11px] text-primary">
                <CheckCircle2 className="size-3" />
                concluída
              </span>
            )}
          </div>
          <h2 className="text-base font-medium break-words">
            <NomeInline
              nome={etapa.nome}
              podeEditar={ehArquiteto}
              onRename={(n) => onRenameEtapa(etapa.id, n)}
            />
          </h2>
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
              <button
                type="button"
                onClick={() =>
                  onEditarCusto({
                    kind: "etapa",
                    id: etapa.id,
                    nome: etapa.nome,
                    unidade: etapa.unidade,
                    quantidade: etapa.quantidade,
                    valor_unitario: etapa.valor_unitario,
                    mao_obra_unitaria: etapa.mao_obra_unitaria,
                    custo_total: etapa.custo_total,
                  })
                }
                aria-label="Custo da etapa"
                title="Custo da etapa"
                className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-primary"
              >
                <Coins className="size-4" />
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

      {/* corpo: filhos da etapa, cada um no seu trilho (depth 1). Subetapas primeiro, depois as
          tarefas diretas; o trilho vertical marca o pertencimento à etapa. */}
      <div className="space-y-1.5 px-2 py-2 sm:px-3">
        {etapa.subetapas.map((se) => (
          <Rail key={se.id} depth={1}>
            <SubetapaBlock
              subetapa={se}
              etapaId={etapa.id}
              wbs={wbs}
              ehArquiteto={ehArquiteto}
              equipesMap={equipesMap}
              onToggle={onToggle}
              onToggleConcluida={onToggleSubetapaConcluida}
              onAddItem={onAddItem}
              onNovaTarefa={onNovaTarefa}
              onEditarCusto={onEditarCusto}
              onFotos={onFotos}
              onEdit={onEdit}
              onDeps={onDeps}
              onRename={onRenameSubetapa}
              onEditDatas={onEditSubetapaDatas}
              onDelete={onDeleteSubetapa}
              onDeleteItem={onDeleteItem}
            />
          </Rail>
        ))}

        {grupos.map((g, gi) => (
          <div key={g.ambiente ?? `__sem_${gi}`}>
            {temAmbiente && (
              <div className="pb-0.5 pl-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground sm:pl-3">
                {g.ambiente ?? "Geral"}
              </div>
            )}
            {g.itens.map((tarefa) => (
              <Rail key={tarefa.id} depth={1}>
                <TarefaBlock
                  tarefa={tarefa}
                  wbs={wbs}
                  depth={1}
                  ehArquiteto={ehArquiteto}
                  equipe={tarefa.equipe_id ? equipesMap.get(tarefa.equipe_id) : undefined}
                  onToggle={onToggle}
                  onAddItem={onAddItem}
                  onFotos={onFotos}
                  onEdit={onEdit}
                  onDeps={onDeps}
                  onDeleteItem={onDeleteItem}
                />
              </Rail>
            ))}
          </div>
        ))}

        {ehArquiteto && (
          <Rail depth={1}>
            <AddMenu
              options={[
                {
                  key: "sub",
                  label: "Subetapa",
                  icon: Layers,
                  placeholder: "Nome da subetapa…",
                  onAdd: (nome) => onAddSubetapa(etapa.id, nome),
                },
                {
                  key: "tarefa",
                  label: "Tarefa",
                  icon: ListChecks,
                  placeholder: "Nome da tarefa…",
                  onAdd: (nome) => onAddItem(etapa.id, nome),
                },
                ...(custeadaFolha
                  ? []
                  : [
                      {
                        key: "custo",
                        label: "Tarefa com custo",
                        icon: Coins,
                        onClick: () =>
                          onNovaTarefa({ etapaId: etapa.id, titulo: `em ${etapa.nome}` }),
                      },
                    ]),
              ]}
            />
          </Rail>
        )}
      </div>
    </Card>
  )
}

function SubetapaBlock({
  subetapa,
  etapaId,
  wbs,
  ehArquiteto,
  equipesMap,
  onToggle,
  onToggleConcluida,
  onAddItem,
  onNovaTarefa,
  onEditarCusto,
  onFotos,
  onEdit,
  onDeps,
  onRename,
  onEditDatas,
  onDelete,
  onDeleteItem,
}: {
  subetapa: SubetapaTree
  etapaId: string
  wbs: WbsMaps
  ehArquiteto: boolean
  equipesMap: Map<string, Equipe>
  onToggle: (item: Item, estado: EstadoItem) => void
  onToggleConcluida: (subetapa: SubetapaTree) => void
  onAddItem: (etapaId: string, nome: string, opts?: AddOpts) => Promise<void>
  onNovaTarefa: (target: NovaTarefaTarget) => void
  onEditarCusto: (target: NodeCustoTarget) => void
  onFotos: (target: FotosTarget) => void
  onEdit: (item: Item) => void
  onDeps: (item: Item) => void
  onRename: (subetapaId: string, nome: string) => Promise<void>
  onEditDatas: (subetapa: SubetapaTree) => void
  onDelete: (subetapa: SubetapaTree) => void
  onDeleteItem: (item: Item) => void
}) {
  const intervalo = formatIntervalo(subetapa.data_inicio, subetapa.data_fim)
  const codigo = wbs.codigo.get(subetapa.id) ?? "—"
  const dur = subetapa.sem_itens ? "" : duracaoLabel(subetapa.data_inicio, subetapa.data_fim)
  const folhas = folhasDe(subetapa.itens)
  const feitos = folhas.filter((s) => s.estado === "concluido").length
  const subtotal = custoSubetapa(subetapa)
  const custeadaFolha = subetapa.sem_itens && (subetapa.custo_total ?? 0) > 0
  const comp = custeadaFolha ? composicaoCusto(subetapa) : null // hint de composição (só na folha)
  return (
    <div>
      {/* banner do galho: identifica a subetapa (ícone Layers) e abre o trilho dos seus filhos */}
      <div className="flex items-center justify-between gap-2 rounded-md bg-muted/40 px-2 py-1.5">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1 font-medium">
              <Layers className="size-3" />
              Subetapa {codigo}
            </span>
            {subetapa.sem_itens && (
              <span
                className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary"
                title="Subetapa sem tarefas: marque como concluída direto. Ao adicionar tarefas, ela passa a somar o progresso delas."
              >
                Marco
              </span>
            )}
            {folhas.length > 0 && (
              <span>
                {feitos}/{folhas.length} feitos
              </span>
            )}
            {subtotal > 0 && <span className="text-primary/80">{brl(subtotal)}</span>}
            {comp && <span>{comp}</span>}
            {intervalo && (
              <span
                className="inline-flex items-center gap-1"
                title={
                  subetapa.sem_itens
                    ? undefined
                    : "Calculado das tarefas: início = a 1ª começa · fim = a última termina"
                }
              >
                <CalendarRange className="size-3" />
                {intervalo}
                {dur && <span className="text-muted-foreground/70">· {dur}</span>}
              </span>
            )}
            {subetapa.sem_itens && subetapa.concluida && (
              <span className="inline-flex items-center gap-1 text-primary">
                <CheckCircle2 className="size-3" />
                concluída
              </span>
            )}
          </div>
          <p className="break-words text-sm font-medium">
            <NomeInline
              nome={subetapa.nome}
              podeEditar={ehArquiteto}
              onRename={(n) => onRename(subetapa.id, n)}
            />
          </p>
        </div>
        {ehArquiteto && (
          <div className="flex shrink-0 items-center">
            {subetapa.sem_itens && (
              <>
                <button
                  type="button"
                  onClick={() => onToggleConcluida(subetapa)}
                  aria-label={subetapa.concluida ? "Marcar como não concluída" : "Marcar como concluída"}
                  title={subetapa.concluida ? "Concluída" : "Marcar como concluída"}
                  className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-primary"
                >
                  {subetapa.concluida ? (
                    <CheckCircle2 className="size-4 text-primary" />
                  ) : (
                    <Circle className="size-4" />
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => onEditDatas(subetapa)}
                  aria-label="Datas da subetapa"
                  title="Datas da subetapa"
                  className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-primary"
                >
                  <CalendarRange className="size-4" />
                </button>
                <button
                  type="button"
                  onClick={() =>
                    onEditarCusto({
                      kind: "subetapa",
                      id: subetapa.id,
                      nome: subetapa.nome,
                      unidade: subetapa.unidade,
                      quantidade: subetapa.quantidade,
                      valor_unitario: subetapa.valor_unitario,
                      mao_obra_unitaria: subetapa.mao_obra_unitaria,
                      custo_total: subetapa.custo_total,
                    })
                  }
                  aria-label="Custo da subetapa"
                  title="Custo da subetapa"
                  className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-primary"
                >
                  <Coins className="size-4" />
                </button>
              </>
            )}
            <button
              type="button"
              onClick={() => onDelete(subetapa)}
              aria-label="Excluir subetapa"
              title="Excluir subetapa"
              className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
            >
              <Trash2 className="size-4" />
            </button>
          </div>
        )}
      </div>

      {subetapa.itens.map((tarefa) => (
        <Rail key={tarefa.id} depth={2}>
          <TarefaBlock
            tarefa={tarefa}
            wbs={wbs}
            depth={2}
            ehArquiteto={ehArquiteto}
            equipe={tarefa.equipe_id ? equipesMap.get(tarefa.equipe_id) : undefined}
            onToggle={onToggle}
            onAddItem={onAddItem}
            onFotos={onFotos}
            onEdit={onEdit}
            onDeps={onDeps}
            onDeleteItem={onDeleteItem}
          />
        </Rail>
      ))}

      {ehArquiteto && (
        <Rail depth={2}>
          <AddMenu
            options={[
              {
                key: "tarefa",
                label: "Tarefa",
                icon: ListChecks,
                placeholder: "Nome da tarefa…",
                onAdd: (nome) => onAddItem(etapaId, nome, { subetapaId: subetapa.id }),
              },
              ...(custeadaFolha
                ? []
                : [
                    {
                      key: "custo",
                      label: "Tarefa com custo",
                      icon: Coins,
                      onClick: () =>
                        onNovaTarefa({
                          etapaId,
                          subetapaId: subetapa.id,
                          titulo: `em ${subetapa.nome}`,
                        }),
                    },
                  ]),
            ]}
          />
        </Rail>
      )}
    </div>
  )
}

function TarefaBlock({
  tarefa,
  wbs,
  depth,
  ehArquiteto,
  equipe,
  onToggle,
  onAddItem,
  onFotos,
  onEdit,
  onDeps,
  onDeleteItem,
}: {
  tarefa: Item
  wbs: WbsMaps
  depth: number
  ehArquiteto: boolean
  equipe?: Equipe
  onToggle: (item: Item, estado: EstadoItem) => void
  onAddItem: (etapaId: string, nome: string, opts?: AddOpts) => Promise<void>
  onFotos: (target: FotosTarget) => void
  onEdit: (item: Item) => void
  onDeps: (item: Item) => void
  onDeleteItem: (item: Item) => void
}) {
  const subs = tarefa.subitens
  const feitos = subs.filter((s) => s.estado === "concluido").length
  const completa = subs.length > 0 && feitos === subs.length
  const codigo = wbs.codigo.get(tarefa.id) ?? "—"
  return (
    <div>
      {/* cabeçalho da tarefa: tarefa-FOLHA (sem sub-itens) ganha o toggle de 3 estados; com
          sub-itens mostra só o progresso (deriva dos filhos). */}
      <div className="flex items-start gap-2 py-1.5 pl-1">
        {subs.length === 0 && (
          <StateToggle
            value={tarefa.estado}
            onChange={(e) => onToggle(tarefa, e)}
            bloqueada={tarefa.bloqueada}
          />
        )}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">
            <span className="mr-1.5 font-display text-[11px] font-normal text-muted-foreground">
              {codigo}
            </span>
            {tarefa.nome}
          </p>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
            {tarefa.bloqueada && (
              <span
                className="inline-flex items-center gap-1 text-[hsl(var(--estado-andamento))]"
                title="Espera as tarefas anteriores terminarem para poder começar"
              >
                <Lock className="size-3" />
                bloqueada
                {tarefa.aguarda.length > 0 && ` · espera ${rotuloAguarda(tarefa.aguarda, wbs)}`}
              </span>
            )}
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
            {equipe && (
              <span className="inline-flex items-center gap-1" title={`Equipe: ${equipe.nome}`}>
                <span
                  className="size-2 shrink-0 rounded-full"
                  style={{ background: equipe.cor }}
                  aria-hidden
                />
                {equipe.nome}
              </span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center">
          {/* dependência/duração só na FOLHA (tarefa sem subitens): um agregador deriva dos filhos */}
          {ehArquiteto && subs.length === 0 && (
            <button
              type="button"
              onClick={() => onDeps(tarefa)}
              aria-label="O que vem antes e duração"
              title="O que vem antes e duração"
              className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-primary"
            >
              <Link2 className="size-4" />
            </button>
          )}
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

      {/* sub-itens do checklist (filhos): cada um no seu trilho (mais um nível de pertencimento).
          Aqui sim o toggle de 3 estados. NOTA (v1): dependências/duração ficam só na tarefa
          top-level (botão Link2 acima) — o backend permite em QUALQUER folha, mas o front não expõe
          deps de subtarefa; como nada aqui cria essa dep, não há inconsistência visível. */}
      {subs.map((s) => (
        <Rail key={s.id} depth={depth + 1}>
          <div className="flex items-center gap-2 py-1.5 pl-1">
            <StateToggle value={s.estado} onChange={(e) => onToggle(s, e)} bloqueada={s.bloqueada} />
            <div className="min-w-0 flex-1">
              <p className="break-words text-sm">
                <span className="mr-1.5 font-display text-[11px] text-muted-foreground">
                  {wbs.codigo.get(s.id) ?? "—"}
                </span>
                {s.nome}
              </p>
              {s.estado === "concluido" && s.concluido_por_nome && (
                <p className="break-words text-[11px] text-muted-foreground">por {s.concluido_por_nome}</p>
              )}
            </div>
            {ehArquiteto && (
              <button
                type="button"
                onClick={() => onEdit(s)}
                aria-label="Cômodo / custo"
                title="Cômodo / custo"
                className="shrink-0 rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-primary"
              >
                <Pencil className="size-4" />
              </button>
            )}
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
        </Rail>
      ))}

      {ehArquiteto && (
        <Rail depth={depth + 1}>
          <AddMenu
            options={[
              {
                key: "subtarefa",
                label: "SubTarefa",
                icon: Plus,
                placeholder: "Nome da subtarefa…",
                // subetapaId espelha o do pai (o backend deriva, mas mantém o item otimista coerente)
                onAdd: (nome) =>
                  onAddItem(tarefa.etapa_id, nome, {
                    parentId: tarefa.id,
                    subetapaId: tarefa.subetapa_id ?? undefined,
                  }),
              },
            ]}
          />
        </Rail>
      )}
    </div>
  )
}

function AddInline({
  placeholder,
  cta,
  onAdd,
  icon: Icon = Plus,
  autoFocus,
}: {
  placeholder: string
  cta: string
  onAdd: (nome: string) => Promise<void>
  icon?: ComponentType<{ className?: string }>
  autoFocus?: boolean
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
        // autoFocus só fora de modal (aqui é a árvore, não um Dialog) — ok pela regra do repo.
        autoFocus={autoFocus}
        value={nome}
        onChange={(e) => setNome(e.target.value)}
        maxLength={300}
        placeholder={placeholder}
        className="h-9 min-w-0 flex-1 border-0 bg-transparent px-1 text-sm focus-visible:ring-0"
      />
      <Button type="submit" size="sm" variant="ghost" className="shrink-0" disabled={!nome.trim()}>
        <Icon className="size-4" />
        {cta}
      </Button>
    </form>
  )
}

/** Opção do "+ Adicionar": ou um quick-add (placeholder+onAdd, input inline) ou uma ação
 * (onClick, ex.: abrir o diálogo de tarefa com custo). */
type AddOption = {
  key: string
  label: string
  icon: ComponentType<{ className?: string }>
  placeholder?: string
  onAdd?: (nome: string) => Promise<void>
  onClick?: () => void
}

/** Um único gatilho "+ Adicionar" por nó (some a poluição dos 2-4 campos sempre-abertos). Clica →
 * mostra as opções válidas daquele nó; escolher um quick-add abre o campo inline (foca e deixa
 * adicionar vários); escolher uma ação (ex. "com custo") dispara o onClick e recolhe. */
function AddMenu({ options }: { options: AddOption[] }) {
  const [aberto, setAberto] = useState(false)
  const [ativo, setAtivo] = useState<AddOption | null>(null)

  if (ativo && ativo.onAdd) {
    return (
      <div className="flex items-center gap-1">
        <AddInline
          placeholder={ativo.placeholder ?? "Nome…"}
          cta={ativo.label}
          icon={ativo.icon}
          onAdd={ativo.onAdd}
          autoFocus
        />
        <button
          type="button"
          onClick={() => {
            setAtivo(null)
            setAberto(false)
          }}
          className="shrink-0 px-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          concluir
        </button>
      </div>
    )
  }

  if (!aberto) {
    // 1 opção de quick-add → abre direto no campo (sem passo de menu) e mostra o nome do nível.
    const solo = options.length === 1 && options[0].onAdd ? options[0] : null
    return (
      <button
        type="button"
        onClick={() => (solo ? setAtivo(solo) : setAberto(true))}
        className="inline-flex items-center gap-1.5 px-1 py-1 text-xs text-muted-foreground transition-colors hover:text-primary"
      >
        <Plus className="size-3.5" />
        {solo ? solo.label : "Adicionar"}
      </button>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-1 py-1">
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          onClick={() => {
            if (o.onClick) {
              o.onClick()
              setAberto(false)
            } else {
              setAtivo(o)
            }
          }}
          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary"
        >
          <o.icon className="size-3.5" />
          {o.label}
        </button>
      ))}
      <button
        type="button"
        onClick={() => setAberto(false)}
        className="px-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
      >
        cancelar
      </button>
    </div>
  )
}

/** Pivot "por cômodo": agrupa as tarefas (de todas as etapas) por ambiente — % e custo por cômodo. */
function VistaAmbientes({
  etapas,
  ambientes,
  onToggle,
  onFotos,
}: {
  etapas: Etapa[]
  ambientes: Ambiente[]
  onToggle: (item: Item, estado: EstadoItem) => void
  onFotos: (target: FotosTarget) => void
}) {
  const etapaNome = new Map(etapas.map((e) => [e.id, e.nome] as const))
  const tarefas = etapas.flatMap(tarefasDaEtapa) // diretas + de subetapas
  const semComodo = tarefas.filter((t) => !t.ambiente_id)
  const grupos: { amb: Ambiente | null; itens: Item[] }[] = [
    ...ambientes
      .map((a) => ({ amb: a as Ambiente | null, itens: tarefas.filter((t) => t.ambiente_id === a.id) }))
      .filter((g) => g.itens.length > 0),
    ...(semComodo.length > 0 ? [{ amb: null, itens: semComodo }] : []),
  ]

  if (grupos.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
        {tarefas.length === 0
          ? "Nenhuma tarefa ainda. Adicione itens nas etapas (na vista “Por etapa”) para agrupá-los por cômodo."
          : "Marque o cômodo das tarefas (no lápis de cada uma) para vê-las agrupadas por ambiente."}
      </p>
    )
  }

  return (
    <div className="space-y-4">
      {grupos.map((g) => {
        const folhas = g.itens.flatMap((t) => (t.subitens.length > 0 ? t.subitens : [t]))
        const feitos = folhas.filter((s) => s.estado === "concluido").length
        const custo = g.itens.reduce((s, t) => s + custoItem(t), 0)
        return (
          <Card key={g.amb?.id ?? "__sem"} className="overflow-hidden">
            <div className="border-b border-border p-4">
              <h2 className="break-words text-base font-medium">{g.amb?.nome ?? "Sem cômodo"}</h2>
              <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-[11px] text-muted-foreground">
                {folhas.length > 0 && (
                  <span className={feitos === folhas.length ? "text-primary" : ""}>
                    {feitos}/{folhas.length} feitos
                  </span>
                )}
                {g.amb?.area_m2 != null && <span>{numFmt(g.amb.area_m2)} m²</span>}
                {custo > 0 && <span className="text-primary/80">{brl(custo)}</span>}
              </div>
            </div>
            <ul className="divide-y divide-border">
              {g.itens.map((t) => {
                const subs = t.subitens
                const fe = subs.filter((s) => s.estado === "concluido").length
                return (
                  <li key={t.id} className="flex items-start gap-3 px-4 py-2.5">
                    {subs.length === 0 ? (
                      <StateToggle
                        value={t.estado}
                        onChange={(e) => onToggle(t, e)}
                        bloqueada={t.bloqueada}
                      />
                    ) : (
                      <span className="mt-1 shrink-0 text-[11px] text-muted-foreground">
                        {fe}/{subs.length}
                      </span>
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="break-words text-sm font-medium">{t.nome}</p>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
                        <span>{etapaNome.get(t.etapa_id) ?? "—"}</span>
                        {t.bloqueada && (
                          <span className="inline-flex items-center gap-1 text-[hsl(var(--estado-andamento))]">
                            <Lock className="size-3" /> bloqueada
                          </span>
                        )}
                        {custoItem(t) > 0 && (
                          <span className="text-primary/80">{brl(custoItem(t))}</span>
                        )}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        onFotos({ parentType: "checklist_item", parentId: t.id, titulo: t.nome })
                      }
                      aria-label="Fotos da tarefa"
                      title="Fotos"
                      className="shrink-0 rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-primary"
                    >
                      <Camera className="size-4" />
                    </button>
                  </li>
                )
              })}
            </ul>
          </Card>
        )
      })}
    </div>
  )
}
