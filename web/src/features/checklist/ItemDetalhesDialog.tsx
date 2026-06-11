import { Loader2 } from "lucide-react"
import { useEffect, useState, type ReactNode } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Combobox } from "@/components/ui/combobox"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import {
  useAtualizarDetalhes,
  useSetItemDatas,
  type Item,
} from "@/features/checklist/checklistApi"
import type { Equipe } from "@/features/equipes/equipesApi"

/** Aceita "1.234,56" (BR), "1234.56" ou "" → number | null (vazio limpa o campo). */
function parseNum(s: string): number | null {
  const t = s.trim()
  if (!t) return null
  // com vírgula = decimal BR (ponto é milhar); sem vírgula = ponto já é o decimal.
  const norm = t.includes(",") ? t.replace(/\./g, "").replace(",", ".") : t
  const n = Number(norm)
  return Number.isFinite(n) ? n : null
}

export function ItemDetalhesDialog({
  obraId,
  item,
  ambientes = [],
  equipes = [],
  onOpenChange,
}: {
  obraId: string
  item: Item | null
  /** nomes de cômodos já cadastrados na obra (autocomplete poka-yoke contra variações). */
  ambientes?: string[]
  /** equipes do escritório (biblioteca nível-tenant) p/ atribuir a tarefa. */
  equipes?: Equipe[]
  onOpenChange: (open: boolean) => void
}) {
  const salvar = useAtualizarDetalhes(obraId)
  const salvarDatas = useSetItemDatas(obraId)
  const [ambiente, setAmbiente] = useState("")
  const [equipeId, setEquipeId] = useState<string | null>(null)
  const [unidade, setUnidade] = useState("")
  const [quantidade, setQuantidade] = useState("")
  const [mo, setMo] = useState("")
  const [mat, setMat] = useState("")
  const [total, setTotal] = useState("")
  const [inicio, setInicio] = useState("")
  const [fim, setFim] = useState("")

  useEffect(() => {
    if (!item) return
    setAmbiente(item.ambiente ?? "")
    setEquipeId(item.equipe_id ?? null)
    setUnidade(item.unidade ?? "")
    setQuantidade(item.quantidade?.toString() ?? "")
    setMo(item.custo_mao_obra?.toString() ?? "")
    setMat(item.custo_material?.toString() ?? "")
    setTotal(item.custo_total?.toString() ?? "")
    setInicio(item.data_inicio ?? "")
    setFim(item.data_fim ?? "")
  }, [item])

  const datasInvalidas = !!inicio && !!fim && fim < inicio
  const salvando = salvar.isPending || salvarDatas.isPending

  async function onSave() {
    if (!item || salvando) return
    if (datasInvalidas) {
      toast.error("A data de fim não pode ser anterior à de início.")
      return
    }
    try {
      await salvar.mutateAsync({
        itemId: item.id,
        patch: {
          ambiente: ambiente.trim() || null,
          equipe_id: equipeId,
          unidade: unidade.trim() || null,
          quantidade: parseNum(quantidade),
          custo_mao_obra: parseNum(mo),
          custo_material: parseNum(mat),
          custo_total: parseNum(total),
        },
      })
      await salvarDatas.mutateAsync({
        itemId: item.id,
        data_inicio: inicio || null,
        data_fim: fim || null,
      })
      toast.success("Item atualizado")
      onOpenChange(false)
    } catch {
      toast.error("Não foi possível salvar.")
    }
  }

  return (
    <Dialog open={item !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Detalhes do item</DialogTitle>
          <DialogDescription className="truncate">{item?.nome}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <Field label="Cômodo / ambiente">
            <Combobox
              value={ambiente}
              onChange={setAmbiente}
              options={ambientes}
              maxLength={120}
              placeholder="Ex.: Cozinha, Banheiro, Sala…"
              emptyHint="Nenhum cômodo cadastrado — digite para criar."
            />
          </Field>
          {equipes.length > 0 && (
            <Field label="Equipe responsável">
              <div className="flex flex-wrap gap-1.5">
                <EquipeChip
                  selecionada={equipeId === null}
                  onClick={() => setEquipeId(null)}
                  label="Sem equipe"
                />
                {equipes.map((eq) => (
                  <EquipeChip
                    key={eq.id}
                    cor={eq.cor}
                    label={eq.nome}
                    selecionada={equipeId === eq.id}
                    onClick={() => setEquipeId(eq.id)}
                  />
                ))}
              </div>
            </Field>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Unidade">
              <Input
                value={unidade}
                onChange={(e) => setUnidade(e.target.value)}
                maxLength={40}
                placeholder="m², un, verba…"
              />
            </Field>
            <Field label="Quantidade">
              <Input
                value={quantidade}
                onChange={(e) => setQuantidade(e.target.value)}
                inputMode="decimal"
                placeholder="0"
              />
            </Field>
          </div>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Mão de obra">
              <Input value={mo} onChange={(e) => setMo(e.target.value)} inputMode="decimal" placeholder="R$" />
            </Field>
            <Field label="Material">
              <Input value={mat} onChange={(e) => setMat(e.target.value)} inputMode="decimal" placeholder="R$" />
            </Field>
            <Field label="Total">
              <Input value={total} onChange={(e) => setTotal(e.target.value)} inputMode="decimal" placeholder="R$" />
            </Field>
          </div>
          <div className="grid grid-cols-1 gap-3 border-t border-border pt-3 sm:grid-cols-2">
            <Field label="Início">
              <Input type="date" value={inicio} onChange={(e) => setInicio(e.target.value)} />
            </Field>
            <Field label="Fim">
              <Input
                type="date"
                value={fim}
                min={inicio || undefined}
                onChange={(e) => setFim(e.target.value)}
              />
            </Field>
          </div>
          {datasInvalidas && (
            <p className="text-xs text-destructive">A data de fim não pode ser anterior à de início.</p>
          )}
        </div>

        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button className="flex-1" disabled={salvando || datasInvalidas} onClick={onSave}>
            {salvando && <Loader2 className="animate-spin" />}
            Salvar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-muted-foreground">{label}</span>
      {children}
    </label>
  )
}

/** Chip selecionável de equipe (com a cor da turma). "Sem equipe" vem sem cor. */
function EquipeChip({
  cor,
  label,
  selecionada,
  onClick,
}: {
  cor?: string
  label: string
  selecionada: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
        selecionada
          ? "border-primary bg-primary/10 text-foreground"
          : "border-border text-muted-foreground hover:text-foreground",
      )}
    >
      <span
        className="size-2.5 shrink-0 rounded-full"
        style={cor ? { background: cor } : { border: "1px solid hsl(var(--border))" }}
        aria-hidden
      />
      {label}
    </button>
  )
}
