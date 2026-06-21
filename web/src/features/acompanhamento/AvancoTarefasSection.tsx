import { Camera, Check, Loader2, Plus, X } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/lib/api"
import { uuidv4 } from "@/lib/uuid"
import type { FotosTarget } from "@/features/anexos/FotosDialog"
import {
  progressoFolha,
  tarefasDaEtapa,
  useChecklist,
  type Etapa,
  type Item,
} from "@/features/checklist/checklistApi"
import {
  useDefinirDiarioTarefa,
  useDiarioTarefas,
  useExcluirDiarioTarefa,
  type DiarioTarefa,
} from "@/features/acompanhamento/diarioTarefaApi"

type Folha = { item: Item; etapa: string }

/** Folhas (tarefas/subtarefas sem filhos) de toda a obra, com o nome da etapa p/ contexto. */
function folhasDaObra(etapas: Etapa[] | undefined): Folha[] {
  const out: Folha[] = []
  for (const e of etapas ?? []) {
    for (const t of tarefasDaEtapa(e)) {
      const leaves = t.subitens.length > 0 ? t.subitens : [t]
      for (const lf of leaves) out.push({ item: lf, etapa: e.nome })
    }
  }
  return out
}

function rotuloItem(it: Item): string {
  return `${it.seq_humano != null ? `#${it.seq_humano} ` : ""}${it.nome}`
}

/**
 * Seção "Avanço das tarefas" dentro do diário: lança o progresso de N folhas (% ou quantidade) e
 * anexa fotos por tarefa. Cada operação é independente (PUT/DELETE imediato) — exige o diário já salvo.
 */
export function AvancoTarefasSection({
  obraId,
  diarioId,
  podeEditar,
  onFotos,
}: {
  obraId: string
  diarioId: string
  podeEditar: boolean
  onFotos: (t: FotosTarget) => void
}) {
  const tree = useChecklist(obraId)
  const medicoes = useDiarioTarefas(obraId, diarioId)
  const definir = useDefinirDiarioTarefa(obraId, diarioId)
  const [addOpen, setAddOpen] = useState(false)

  const folhas = useMemo(() => folhasDaObra(tree.data?.etapas), [tree.data])
  const lista = medicoes.data ?? []
  const medidos = new Set(lista.map((m) => m.item_id))
  const disponiveis = folhas.filter((f) => !medidos.has(f.item.id))

  async function adicionar(f: Folha) {
    setAddOpen(false)
    try {
      // começa no avanço ATUAL da folha (snapshot continua de onde está); o usuário ajusta na linha.
      await definir.mutateAsync({
        id: uuidv4(),
        item_id: f.item.id,
        progresso_pct: Math.round(progressoFolha(f.item) * 100),
      })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível adicionar a tarefa.")
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-border p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">Avanço das tarefas</span>
        {lista.length > 0 && (
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
            {lista.length} tarefa{lista.length > 1 ? "s" : ""}
          </span>
        )}
      </div>

      {lista.length > 0 && (
        <ul className="space-y-2">
          {lista.map((m) => (
            <MedicaoRow
              key={m.id}
              obraId={obraId}
              diarioId={diarioId}
              m={m}
              podeEditar={podeEditar}
              onFotos={onFotos}
            />
          ))}
        </ul>
      )}

      {!podeEditar ? (
        lista.length === 0 && (
          <p className="text-[11px] text-muted-foreground">Nenhum avanço lançado neste dia.</p>
        )
      ) : tree.isLoading ? (
        <div className="flex justify-center py-2">
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        </div>
      ) : addOpen ? (
        <div className="space-y-1.5">
          <select
            autoFocus
            className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
            defaultValue=""
            onChange={(e) => {
              const f = disponiveis.find((d) => d.item.id === e.target.value)
              if (f) void adicionar(f)
            }}
          >
            <option value="" disabled>
              Escolha uma tarefa…
            </option>
            {disponiveis.map((f) => (
              <option key={f.item.id} value={f.item.id}>
                {f.etapa} › {rotuloItem(f.item)}
              </option>
            ))}
          </select>
          {disponiveis.length === 0 && (
            <p className="text-[11px] text-muted-foreground">
              Todas as tarefas já têm avanço lançado neste dia.
            </p>
          )}
          <button
            type="button"
            onClick={() => setAddOpen(false)}
            className="text-[11px] font-medium text-muted-foreground hover:underline"
          >
            Cancelar
          </button>
        </div>
      ) : (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="w-full"
          disabled={definir.isPending}
          onClick={() => setAddOpen(true)}
        >
          {definir.isPending ? <Loader2 className="animate-spin" /> : <Plus />}
          Adicionar tarefa
        </Button>
      )}
    </div>
  )
}

/** Uma linha de medição: entrada por QUANTIDADE quando a tarefa tem unidade/qtd; senão por %. */
function MedicaoRow({
  obraId,
  diarioId,
  m,
  podeEditar,
  onFotos,
}: {
  obraId: string
  diarioId: string
  m: DiarioTarefa
  podeEditar: boolean
  onFotos: (t: FotosTarget) => void
}) {
  const definir = useDefinirDiarioTarefa(obraId, diarioId)
  const excluir = useExcluirDiarioTarefa(obraId, diarioId)
  const porQtd = m.quantidade != null && m.quantidade > 0 && !!m.unidade
  // entrada por qtd: usa a qtd executada; se a medição só tem %, deriva a qtd do % (não mostra 0).
  const valorAtual = porQtd
    ? (m.qtd_executada ?? (m.quantidade ? (m.progresso_pct / 100) * m.quantidade : 0))
    : m.progresso_pct
  const [draft, setDraft] = useState(String(Math.round(valorAtual * 100) / 100))
  // re-sincroniza com o servidor quando a medição muda (refetch/clamp/outra aba) → some o "Salvar"
  // fantasma e o input para de divergir do badge. Não dispara enquanto o usuário digita (valorAtual
  // só muda no refetch).
  useEffect(() => setDraft(String(Math.round(valorAtual * 100) / 100)), [valorAtual])

  const num = Number(draft.replace(",", "."))
  const valido = draft.trim() !== "" && !Number.isNaN(num) && num >= 0
  // % previsto a partir do rascunho (espelha derivar_pct do backend).
  const pctPrev = porQtd
    ? m.quantidade && m.quantidade > 0
      ? Math.min(100, Math.max(0, (num / m.quantidade) * 100))
      : 0
    : Math.min(100, Math.max(0, num))
  const mudou = valido && Math.abs(num - valorAtual) > 1e-9

  async function salvar() {
    if (!valido || !mudou) return
    try {
      await definir.mutateAsync({
        id: m.id,
        item_id: m.item_id,
        ...(porQtd ? { qtd_executada: num } : { progresso_pct: num }),
      })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar o avanço.")
      setDraft(String(valorAtual))
    }
  }

  async function remover() {
    try {
      await excluir.mutateAsync(m.id)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível remover.")
    }
  }

  return (
    <li className="space-y-1.5 rounded-md border border-border px-2.5 py-2">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">
            {m.item_seq != null ? `#${m.item_seq} ` : ""}
            {m.item_nome}
          </p>
          {m.etapa_nome && (
            <p className="truncate text-[11px] text-muted-foreground">{m.etapa_nome}</p>
          )}
        </div>
        <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium tabular-nums text-primary">
          {Math.round(pctPrev)}%
        </span>
        {podeEditar && (
          <button
            type="button"
            aria-label="Remover tarefa"
            onClick={remover}
            disabled={excluir.isPending}
            className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:text-destructive"
          >
            <X className="size-4" />
          </button>
        )}
      </div>

      <div className="flex items-center gap-2">
        {podeEditar ? (
          <>
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={salvar}
              onKeyDown={(e) => e.key === "Enter" && salvar()}
              inputMode="decimal"
              className="h-8 w-24 text-sm"
            />
            <span className="text-xs text-muted-foreground">
              {porQtd ? `de ${m.quantidade} ${m.unidade}` : "%"}
            </span>
            {mudou && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8"
                disabled={definir.isPending}
                onClick={salvar}
              >
                {definir.isPending ? <Loader2 className="animate-spin" /> : <Check />}
              </Button>
            )}
          </>
        ) : (
          <span className="text-xs text-muted-foreground">
            {porQtd ? `${m.qtd_executada ?? 0} de ${m.quantidade} ${m.unidade}` : `${m.progresso_pct}%`}
          </span>
        )}
        <button
          type="button"
          onClick={() => onFotos({ parentType: "diario_tarefa", parentId: m.id, titulo: m.item_nome })}
          className="ml-auto inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
        >
          <Camera className="size-3.5" />
          {m.n_fotos > 0 ? `${m.n_fotos} foto${m.n_fotos > 1 ? "s" : ""}` : "Fotos"}
        </button>
      </div>
    </li>
  )
}
