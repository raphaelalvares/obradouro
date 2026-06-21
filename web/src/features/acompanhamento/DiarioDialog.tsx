import { Loader2, Minus, Plus, X } from "lucide-react"
import { useEffect, useRef, useState, type FormEvent } from "react"
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
import { Textarea } from "@/components/ui/textarea"
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import { hojeISO } from "@/features/comercial/format"
import type { FotosTarget } from "@/features/anexos/FotosDialog"
import {
  useCriarFuncao,
  useFuncoesObra,
  type FuncaoSimples,
} from "@/features/funcoes/funcoesApi"
import { AvancoTarefasSection } from "@/features/acompanhamento/AvancoTarefasSection"
import {
  useAtualizarDiario,
  useCriarDiario,
  type Diario,
} from "@/features/acompanhamento/acompanhamentoApi"

const CLIMAS = ["Ensolarado", "Nublado", "Chuva", "Garoa", "Vento forte"]

type ItemEfetivo = { funcao_id: string; nome: string; qtd: number }

/** Chave estável da quebra do efetivo (p/ detectar se mudou — a ordem é estável, sem reordenação). */
function efetivoKey(itens: ItemEfetivo[]) {
  return JSON.stringify(itens.map((i) => [i.funcao_id, i.qtd]))
}

/** Cria/edita uma entrada do diário de obra. entry=null → nova entrada. */
export function DiarioDialog({
  obraId,
  open,
  entry,
  podeGerenciar,
  podeEditar,
  onFotos,
  onOpenChange,
}: {
  obraId: string
  open: boolean
  entry: Diario | null
  /** arquiteto → pode cadastrar funções na hora (cadastro rápido inline). */
  podeGerenciar: boolean
  /** quem abre o diário pode editar avanço/fotos (executor: arquiteto qualquer ou autor do diário). */
  podeEditar: boolean
  onFotos: (t: FotosTarget) => void
  onOpenChange: (open: boolean) => void
}) {
  const criar = useCriarDiario(obraId)
  const atualizar = useAtualizarDiario(obraId)
  // entrada salva (existente OU recém-criada): habilita a seção de avanço/fotos, que precisa do id.
  const [criada, setCriada] = useState<Diario | null>(null)
  const entryAtual = entry ?? criada
  const [data, setData] = useState("")
  const [texto, setTexto] = useState("")
  const [clima, setClima] = useState("")
  const [efetivo, setEfetivo] = useState<ItemEfetivo[]>([])
  // chave do efetivo no momento da abertura → no salvar só reenviamos efetivo_itens se MUDOU. Assim,
  // editar só o texto/clima de uma entrada antiga nunca re-valida o efetivo (não quebra com 404 se um
  // cargo daquela entrada foi excluído depois).
  const efetivoInicial = useRef("")

  useEffect(() => {
    if (!open) return
    setCriada(null)
    setData(entry?.data ?? hojeISO())
    setTexto(entry?.texto ?? "")
    setClima(entry?.clima ?? "")
    const carregado =
      entry?.efetivo_itens?.map((i) => ({ funcao_id: i.funcao_id, nome: i.nome, qtd: i.qtd })) ?? []
    setEfetivo(carregado)
    efetivoInicial.current = efetivoKey(carregado)
  }, [open, entry])

  const salvando = criar.isPending || atualizar.isPending

  async function onSave() {
    if (salvando) return
    if (!texto.trim()) {
      toast.error("Escreva o relato do dia.")
      return
    }
    const base = { data, texto: texto.trim(), clima: clima.trim() || null }
    // entrada nova → sempre manda o efetivo; edição → só se mudou (poupa re-validação/escrita).
    const mudouEfetivo = !entryAtual || efetivoKey(efetivo) !== efetivoInicial.current
    const payload = mudouEfetivo
      ? { ...base, efetivo_itens: efetivo.map(({ funcao_id, qtd }) => ({ funcao_id, qtd })) }
      : base
    try {
      if (entryAtual) {
        await atualizar.mutateAsync({ id: entryAtual.id, patch: payload })
        toast.success("Entrada atualizada")
      } else {
        // não fecha: vira "edição" da recém-criada → a seção de avanço/fotos passa a aparecer.
        const nova = await criar.mutateAsync(payload)
        setCriada(nova)
        toast.success("Entrada registrada — agora lance o avanço das tarefas")
      }
      efetivoInicial.current = efetivoKey(efetivo)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{entryAtual ? "Editar entrada" : "Nova entrada do diário"}</DialogTitle>
          <DialogDescription>O que aconteceu na obra neste dia.</DialogDescription>
        </DialogHeader>

        <div className="max-h-[60vh] space-y-3 overflow-y-auto pr-1">
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs text-muted-foreground">Data</span>
              <Input type="date" value={data} onChange={(e) => setData(e.target.value)} />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs text-muted-foreground">Clima</span>
              <Input
                value={clima}
                onChange={(e) => setClima(e.target.value)}
                maxLength={60}
                list="diario-climas"
                placeholder="Ex.: Ensolarado, Chuva…"
              />
              <datalist id="diario-climas">
                {CLIMAS.map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
            </label>
          </div>

          <EfetivoEditor
            obraId={obraId}
            ativo={open}
            podeGerenciar={podeGerenciar}
            itens={efetivo}
            onChange={setEfetivo}
          />

          <label className="block">
            <span className="mb-1 block text-xs text-muted-foreground">Relato</span>
            <Textarea
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              maxLength={4000}
              rows={5}
              placeholder="Serviços executados, ocorrências, entregas, decisões…"
            />
          </label>

          {podeEditar &&
            (entryAtual ? (
              <AvancoTarefasSection
                obraId={obraId}
                diarioId={entryAtual.id}
                podeEditar={podeEditar}
                onFotos={onFotos}
              />
            ) : (
              <p className="rounded-lg border border-dashed border-border px-3 py-2 text-[11px] text-muted-foreground">
                Salve a entrada para lançar o avanço das tarefas e anexar fotos.
              </p>
            ))}
        </div>

        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
            {entryAtual ? "Fechar" : "Cancelar"}
          </Button>
          <Button className="flex-1" disabled={salvando} onClick={onSave}>
            {salvando && <Loader2 className="animate-spin" />}
            {entryAtual ? "Salvar alterações" : "Salvar"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/**
 * Editor do efetivo do dia: escolha FUNÇÃO + QUANTIDADE (poka-yoke — sem digitar número solto). As
 * funções vêm da biblioteca do escritório (picker por obra; funciona p/ prestador também). Arquiteto
 * pode cadastrar uma função nova na hora (cadastro rápido inline).
 */
function EfetivoEditor({
  obraId,
  ativo,
  podeGerenciar,
  itens,
  onChange,
}: {
  obraId: string
  ativo: boolean
  podeGerenciar: boolean
  itens: ItemEfetivo[]
  onChange: (itens: ItemEfetivo[]) => void
}) {
  const funcoes = useFuncoesObra(obraId, ativo)
  const criar = useCriarFuncao()
  const [nova, setNova] = useState("")

  const total = itens.reduce((s, i) => s + i.qtd, 0)
  const lista = funcoes.data ?? []
  const disponiveis = lista.filter((f) => !itens.some((i) => i.funcao_id === f.id))

  function add(f: FuncaoSimples) {
    if (itens.some((i) => i.funcao_id === f.id)) return
    onChange([...itens, { funcao_id: f.id, nome: f.nome, qtd: 1 }])
  }
  function setQtd(id: string, q: number) {
    const v = Math.min(9999, Math.max(1, q))
    onChange(itens.map((i) => (i.funcao_id === id ? { ...i, qtd: v } : i)))
  }
  function remove(id: string) {
    onChange(itens.filter((i) => i.funcao_id !== id))
  }

  async function criarEAdd(e: FormEvent) {
    e.preventDefault()
    const limpo = nova.trim()
    if (!limpo) return
    // se já existe uma função com esse nome no picker, só adiciona (evita 409 desnecessário).
    const existente = lista.find((f) => f.nome.trim().toLowerCase() === limpo.toLowerCase())
    if (existente) {
      add(existente)
      setNova("")
      return
    }
    try {
      const f = await criar.mutateAsync({ nome: limpo })
      onChange([...itens, { funcao_id: f.id, nome: f.nome, qtd: 1 }])
      setNova("")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível criar a função.")
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-border p-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">Efetivo do dia</span>
        {total > 0 && (
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
            {total} pessoa{total > 1 ? "s" : ""}
          </span>
        )}
      </div>

      {itens.length > 0 && (
        <ul className="space-y-1.5">
          {itens.map((it) => (
            <li
              key={it.funcao_id}
              className="flex items-center gap-2 rounded-md border border-border px-2.5 py-1.5"
            >
              <span className="min-w-0 flex-1 truncate text-sm">{it.nome}</span>
              <div className="flex items-center gap-1">
                <StepBtn
                  label="Menos um"
                  disabled={it.qtd <= 1}
                  onClick={() => setQtd(it.funcao_id, it.qtd - 1)}
                >
                  <Minus className="size-3.5" />
                </StepBtn>
                <span className="w-7 text-center text-sm tabular-nums">{it.qtd}</span>
                <StepBtn label="Mais um" onClick={() => setQtd(it.funcao_id, it.qtd + 1)}>
                  <Plus className="size-3.5" />
                </StepBtn>
              </div>
              <button
                type="button"
                aria-label={`Remover ${it.nome}`}
                onClick={() => remove(it.funcao_id)}
                className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:text-destructive"
              >
                <X className="size-4" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {funcoes.isError ? (
        <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
          <span>Não foi possível carregar as funções.</span>
          <button
            type="button"
            onClick={() => void funcoes.refetch()}
            className="font-medium text-primary hover:underline"
          >
            Tentar de novo
          </button>
        </div>
      ) : funcoes.isLoading ? (
        <div className="flex justify-center py-2">
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        </div>
      ) : disponiveis.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {disponiveis.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => add(f)}
              className="inline-flex items-center gap-1 rounded-full border border-border px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
            >
              <Plus className="size-3" />
              {f.nome}
            </button>
          ))}
        </div>
      ) : (
        lista.length === 0 && (
          <p className="text-[11px] text-muted-foreground">
            {podeGerenciar
              ? "Cadastre as funções/cargos abaixo para registrar o efetivo."
              : "Nenhuma função cadastrada pelo arquiteto ainda."}
          </p>
        )
      )}

      {podeGerenciar && (
        <form onSubmit={criarEAdd} className="flex items-center gap-2 pt-1">
          <Input
            value={nova}
            onChange={(e) => setNova(e.target.value)}
            maxLength={120}
            placeholder="Nova função (ex.: Pedreiro)…"
            className="h-8 min-w-0 flex-1 text-sm"
          />
          <Button
            type="submit"
            size="sm"
            variant="outline"
            disabled={!nova.trim() || criar.isPending}
            className="shrink-0"
          >
            {criar.isPending ? <Loader2 className="animate-spin" /> : <Plus />}
          </Button>
        </form>
      )}
    </div>
  )
}

function StepBtn({
  label,
  disabled,
  onClick,
  children,
}: {
  label: string
  disabled?: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex size-7 items-center justify-center rounded-md border border-border text-muted-foreground transition-colors",
        disabled ? "opacity-40" : "hover:border-primary hover:text-foreground",
      )}
    >
      {children}
    </button>
  )
}
