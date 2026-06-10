import { Check, Link2, Loader2, Plus, Trash2 } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError } from "@/lib/api"
import {
  useAddDep,
  useExcluirDep,
  useSetDuracao,
  type Dependencia,
  type Etapa,
  type Item,
} from "@/features/checklist/checklistApi"

const rotulo = (t: Item) => `${t.seq_humano != null ? `#${t.seq_humano} ` : ""}${t.nome}`

/**
 * Gerencia as DEPENDÊNCIAS (predecessoras FS) e a DURAÇÃO de uma tarefa top-level. O select de
 * candidatos já EXCLUI a própria tarefa, as predecessoras existentes e os descendentes (poka-yoke:
 * não oferece opção que criaria ciclo); o backend é o backstop e devolve mensagem limpa.
 */
export function DependenciasDialog({
  obraId,
  tarefa,
  etapas,
  dependencias,
  onOpenChange,
}: {
  obraId: string
  tarefa: Item | null
  etapas: Etapa[]
  dependencias: Dependencia[]
  onOpenChange: (open: boolean) => void
}) {
  const addDep = useAddDep(obraId)
  const excluirDep = useExcluirDep(obraId)
  const setDuracao = useSetDuracao(obraId)

  const [novoPred, setNovoPred] = useState("")
  const [lag, setLag] = useState("")
  const [dur, setDur] = useState("")

  // semeia a duração ao abrir/trocar de tarefa
  useEffect(() => {
    setDur(tarefa?.duracao_dias != null ? String(tarefa.duracao_dias) : "")
    setNovoPred("")
    setLag("")
  }, [tarefa])

  const tops = useMemo(() => etapas.flatMap((e) => e.itens), [etapas])
  const byId = useMemo(() => new Map(tops.map((t) => [t.id, t])), [tops])

  const minhasPreds = useMemo(
    () => dependencias.filter((d) => d.sucessora_id === tarefa?.id),
    [dependencias, tarefa],
  )

  // descendentes desta tarefa (segue predecessora→sucessora) p/ não oferecer ciclo no select
  const descend = useMemo(() => {
    const out = new Set<string>()
    if (!tarefa) return out
    const adj = new Map<string, string[]>()
    for (const d of dependencias) {
      const arr = adj.get(d.predecessora_id) ?? []
      arr.push(d.sucessora_id)
      adj.set(d.predecessora_id, arr)
    }
    const stack = [tarefa.id]
    while (stack.length) {
      const n = stack.pop() as string
      for (const s of adj.get(n) ?? []) {
        if (!out.has(s)) {
          out.add(s)
          stack.push(s)
        }
      }
    }
    return out
  }, [dependencias, tarefa])

  const candidatos = useMemo(() => {
    const jaPred = new Set(minhasPreds.map((d) => d.predecessora_id))
    return tops.filter((t) => t.id !== tarefa?.id && !jaPred.has(t.id) && !descend.has(t.id))
  }, [tops, minhasPreds, descend, tarefa])

  if (!tarefa) return null

  async function adicionar() {
    if (!novoPred || !tarefa) return
    try {
      await addDep.mutateAsync({
        predecessora_id: novoPred,
        sucessora_id: tarefa.id,
        lag_dias: Math.max(0, Number(lag) || 0), // sem lead negativo (FS terminar→iniciar)
      })
      setNovoPred("")
      setLag("")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível adicionar.")
    }
  }

  async function remover(depId: string) {
    try {
      await excluirDep.mutateAsync(depId)
    } catch {
      toast.error("Não foi possível remover.")
    }
  }

  async function salvarDuracao() {
    if (!tarefa) return
    const v = dur.trim() ? Math.max(1, Number(dur.replace(",", ".")) || 0) : null
    try {
      await setDuracao.mutateAsync({ itemId: tarefa.id, duracao_dias: v })
      toast.success("Duração salva")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar.")
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="break-words">O que vem antes · {tarefa.nome}</DialogTitle>
          <DialogDescription>
            Diga quais tarefas precisam <strong>terminar antes</strong> desta começar. Enquanto elas
            não estiverem concluídas, esta fica <strong>bloqueada</strong>. Depois toque em “Recalcular
            datas” no topo que o sistema encaixa o cronograma sozinho.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          {/* duração */}
          <div className="space-y-1.5">
            <Label htmlFor="dep-dur">Quantos dias esta tarefa leva?</Label>
            <div className="flex gap-2">
              <Input
                id="dep-dur"
                inputMode="numeric"
                value={dur}
                onChange={(e) => setDur(e.target.value)}
                placeholder="ex.: 5"
                className="flex-1"
              />
              <Button
                type="button"
                variant="outline"
                onClick={salvarDuracao}
                disabled={setDuracao.isPending}
              >
                {setDuracao.isPending ? <Loader2 className="animate-spin" /> : <Check />}
                Salvar
              </Button>
            </div>
            <p className="text-[11px] text-muted-foreground">
              É o tamanho da barra no “Recalcular datas”. Pode deixar em branco — aí mantém as datas
              atuais.
            </p>
          </div>

          {/* predecessoras atuais */}
          <div className="space-y-2">
            <Label>Esta tarefa só começa depois de:</Label>
            {minhasPreds.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
                Nada ainda — pode começar a qualquer momento.
              </p>
            ) : (
              <ul className="space-y-1.5">
                {minhasPreds.map((d) => {
                  const p = byId.get(d.predecessora_id)
                  return (
                    <li
                      key={d.id}
                      className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm"
                    >
                      <Link2 className="size-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 break-words">
                        {p ? rotulo(p) : "tarefa removida"}
                        {d.lag_dias > 0 && (
                          <span className="text-muted-foreground">
                            {" "}
                            · espera {d.lag_dias} dia{d.lag_dias > 1 ? "s" : ""} depois
                          </span>
                        )}
                      </span>
                      <button
                        type="button"
                        onClick={() => void remover(d.id)}
                        aria-label="Remover dependência"
                        className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:text-destructive"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          {/* adicionar uma tarefa que precisa terminar antes */}
          {candidatos.length > 0 ? (
            <div className="space-y-2 border-t border-border pt-4">
              <Label htmlFor="dep-pred">O que precisa terminar antes?</Label>
              <select
                id="dep-pred"
                value={novoPred}
                onChange={(e) => setNovoPred(e.target.value)}
                className="flex h-10 w-full min-w-0 rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="">Escolher tarefa…</option>
                {candidatos.map((t) => (
                  <option key={t.id} value={t.id}>
                    {rotulo(t)}
                  </option>
                ))}
              </select>
              {/* a "folga" vira frase: esperar N dias depois que a anterior terminar (opcional) */}
              <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                <span className="shrink-0">Esperar</span>
                <Input
                  aria-label="Dias de espera depois que a anterior terminar"
                  inputMode="numeric"
                  value={lag}
                  onChange={(e) => setLag(e.target.value)}
                  placeholder="0"
                  className="w-16 text-center"
                />
                <span className="shrink-0">dia(s) depois que ela terminar</span>
              </div>
              <Button
                type="button"
                onClick={adicionar}
                disabled={!novoPred || addDep.isPending}
                className="w-full sm:w-auto"
              >
                {addDep.isPending ? <Loader2 className="animate-spin" /> : <Plus />}
                Adicionar
              </Button>
            </div>
          ) : (
            <p className="border-t border-border pt-4 text-xs text-muted-foreground">
              Não há outras tarefas para encaixar antes desta.
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
