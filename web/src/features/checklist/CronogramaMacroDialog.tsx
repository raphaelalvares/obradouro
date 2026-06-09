import { CalendarRange, Loader2 } from "lucide-react"
import { useEffect, useState } from "react"
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
import { useAplicarCronograma, type Etapa } from "@/features/checklist/checklistApi"
import {
  distribuirIgual,
  duracaoDias,
  fimPorDuracao,
  formatBR,
  type UnidadeBase,
  type UnidadeCronograma,
} from "@/features/checklist/cronograma"
import type { Obra } from "@/features/obras/obrasApi"

// Unidades distribuídas: cada TAREFA (item top-level) é uma unidade; etapa SEM tarefas vira 1 unidade.
function montarUnidades(etapas: Etapa[]): UnidadeBase[] {
  const us: UnidadeBase[] = []
  for (const e of etapas) {
    if (e.itens.length > 0) {
      for (const t of e.itens) {
        us.push({ tipo: "item", id: t.id, etapaId: e.id, etapaNome: e.nome, label: t.nome })
      }
    } else {
      us.push({
        tipo: "etapa",
        id: e.id,
        etapaId: e.id,
        etapaNome: e.nome,
        label: "(etapa sem tarefas)",
      })
    }
  }
  return us
}

export function CronogramaMacroDialog({
  obraId,
  obra,
  etapas,
  open,
  onOpenChange,
}: {
  obraId: string
  obra: Obra | undefined
  etapas: Etapa[]
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const aplicar = useAplicarCronograma(obraId)
  const [inicio, setInicio] = useState("")
  const [modo, setModo] = useState<"dias" | "termino">("dias")
  const [dias, setDias] = useState("30")
  const [termino, setTermino] = useState("")
  const [linhas, setLinhas] = useState<UnidadeCronograma[] | null>(null)

  // (re)semeia ao abrir: usa a janela já salva na obra, se houver.
  useEffect(() => {
    if (!open) return
    setInicio(obra?.data_inicio ?? "")
    setLinhas(null)
    if (obra?.data_fim) {
      setModo("termino")
      setTermino(obra.data_fim)
    } else {
      setModo("dias")
      setDias("30")
      setTermino("")
    }
  }, [open, obra?.data_inicio, obra?.data_fim])

  // janela calculada da obra a partir das entradas
  const totalDias =
    inicio && modo === "dias"
      ? Math.max(0, Math.floor(Number(dias) || 0))
      : inicio && termino && termino >= inicio
        ? duracaoDias(inicio, termino)
        : 0
  const terminoCalc = inicio && totalDias > 0 ? fimPorDuracao(inicio, totalDias) : ""
  const janelaOk = !!inicio && totalDias > 0

  function gerar() {
    if (!janelaOk) {
      toast.error("Informe o início e o prazo da obra.")
      return
    }
    const unidades = montarUnidades(etapas)
    if (unidades.length === 0) {
      toast.error("Não há tarefas para distribuir.")
      return
    }
    setLinhas(distribuirIgual(unidades, inicio, totalDias))
  }

  function patchLinha(idx: number, patch: Partial<UnidadeCronograma>) {
    setLinhas((ls) => (ls ? ls.map((l, i) => (i === idx ? { ...l, ...patch } : l)) : ls))
  }
  function mudarInicio(idx: number, v: string, dur: number) {
    patchLinha(idx, { inicio: v, fim: v ? fimPorDuracao(v, dur) : "" })
  }
  function mudarFim(idx: number, ini: string, v: string) {
    patchLinha(idx, { fim: v, dias: ini && v && v >= ini ? duracaoDias(ini, v) : 1 })
  }
  function mudarDias(idx: number, ini: string, v: string) {
    const n = Math.max(1, Math.floor(Number(v) || 1))
    patchLinha(idx, { dias: n, fim: ini ? fimPorDuracao(ini, n) : "" })
  }

  // janela efetiva da prévia (min início / max fim) + validação
  const algumaInvalida = !!linhas?.some((l) => !l.inicio || !l.fim || l.fim < l.inicio)
  const previaInicio = linhas?.length ? linhas.reduce((m, l) => (l.inicio < m ? l.inicio : m), linhas[0].inicio) : ""
  const previaFim = linhas?.length ? linhas.reduce((m, l) => (l.fim > m ? l.fim : m), linhas[0].fim) : ""

  async function onAplicar() {
    if (!linhas || !linhas.length || algumaInvalida) return
    try {
      await aplicar.mutateAsync({
        obra_data_inicio: previaInicio || null,
        obra_data_fim: previaFim || null,
        entradas: linhas.map((l) => ({
          tipo: l.tipo,
          id: l.id,
          data_inicio: l.inicio,
          data_fim: l.fim,
        })),
      })
      toast.success("Cronograma aplicado")
      onOpenChange(false)
    } catch {
      toast.error("Não foi possível aplicar o cronograma.")
    }
  }

  // agrupa as linhas por etapa só p/ exibir o cabeçalho da fase na prévia
  const grupos: { etapaId: string; etapaNome: string; itens: { l: UnidadeCronograma; idx: number }[] }[] = []
  linhas?.forEach((l, idx) => {
    const ult = grupos[grupos.length - 1]
    if (ult && ult.etapaId === l.etapaId) ult.itens.push({ l, idx })
    else grupos.push({ etapaId: l.etapaId, etapaNome: l.etapaNome, itens: [{ l, idx }] })
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-xl">
            <CalendarRange className="size-5 text-primary" /> Cronograma macro
          </DialogTitle>
          <DialogDescription>
            Defina a janela da obra; o sistema divide o prazo igualmente entre as tarefas. Ajuste a
            prévia antes de aplicar.
          </DialogDescription>
        </DialogHeader>

        {/* passo 1: janela da obra */}
        <div className="space-y-3 rounded-xl border border-border p-3">
          <label className="block">
            <span className="mb-1 block text-xs text-muted-foreground">Início da obra</span>
            <Input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} />
          </label>

          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              variant={modo === "dias" ? "default" : "outline"}
              className="flex-1"
              onClick={() => setModo("dias")}
            >
              Por duração
            </Button>
            <Button
              type="button"
              size="sm"
              variant={modo === "termino" ? "default" : "outline"}
              className="flex-1"
              onClick={() => setModo("termino")}
            >
              Por término
            </Button>
          </div>

          {modo === "dias" ? (
            <label className="block">
              <span className="mb-1 block text-xs text-muted-foreground">Duração (dias)</span>
              <Input
                type="number"
                min={1}
                value={dias}
                onChange={(e) => setDias(e.target.value)}
                placeholder="30"
              />
            </label>
          ) : (
            <label className="block">
              <span className="mb-1 block text-xs text-muted-foreground">Término</span>
              <Input
                type="date"
                value={termino}
                min={inicio || undefined}
                onChange={(e) => setTermino(e.target.value)}
              />
            </label>
          )}

          <p className="text-xs text-muted-foreground">
            {janelaOk ? (
              <>
                Obra: <span className="text-foreground">{formatBR(inicio)}</span> →{" "}
                <span className="text-foreground">{formatBR(terminoCalc)}</span> ·{" "}
                <span className="text-primary">{totalDias} dia(s)</span>
              </>
            ) : (
              "Preencha o início e o prazo."
            )}
          </p>

          <Button type="button" variant="outline" className="w-full" disabled={!janelaOk} onClick={gerar}>
            {linhas ? "Refazer prévia" : "Gerar prévia"}
          </Button>
        </div>

        {/* passo 2: prévia editável */}
        {linhas && (
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                Prévia — ajuste qualquer campo ({linhas.length} tarefa(s))
              </span>
              <span className={algumaInvalida ? "text-destructive" : "text-primary"}>
                {previaInicio && previaFim
                  ? `${formatBR(previaInicio)} → ${formatBR(previaFim)} · ${duracaoDias(previaInicio, previaFim)} dia(s)`
                  : ""}
              </span>
            </div>

            <div className="space-y-3">
              {grupos.map((g) => (
                <div key={g.etapaId} className="rounded-lg border border-border">
                  <div className="border-b border-border bg-muted/30 px-3 py-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                    {g.etapaNome}
                  </div>
                  <div className="divide-y divide-border">
                    {g.itens.map(({ l, idx }) => {
                      const invalida = !l.inicio || !l.fim || l.fim < l.inicio
                      return (
                        <div key={l.id} className="px-3 py-2">
                          <p className="truncate text-sm" title={l.label}>
                            {l.label}
                          </p>
                          <div className="mt-1.5 grid grid-cols-[1fr_1fr_4.5rem] gap-2">
                            <Input
                              type="date"
                              className="h-9"
                              value={l.inicio}
                              onChange={(e) => mudarInicio(idx, e.target.value, l.dias)}
                            />
                            <Input
                              type="date"
                              className="h-9"
                              value={l.fim}
                              min={l.inicio || undefined}
                              onChange={(e) => mudarFim(idx, l.inicio, e.target.value)}
                            />
                            <Input
                              type="number"
                              min={1}
                              className="h-9"
                              value={l.dias}
                              onChange={(e) => mudarDias(idx, l.inicio, e.target.value)}
                              aria-label="dias"
                            />
                          </div>
                          {invalida && (
                            <p className="mt-1 text-[11px] text-destructive">
                              Preencha início e fim (fim ≥ início).
                            </p>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            className="flex-1"
            disabled={!linhas || !linhas.length || algumaInvalida || aplicar.isPending}
            onClick={onAplicar}
          >
            {aplicar.isPending && <Loader2 className="animate-spin" />}
            Aplicar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
