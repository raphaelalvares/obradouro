import { BookOpen, Loader2 } from "lucide-react"
import { useEffect, useState, type FormEvent } from "react"
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
import { cn } from "@/lib/utils"
import { ApiError } from "@/lib/api"
import { formatBRL } from "@/features/comercial/format"
import { useTemplate, useTemplates } from "@/features/catalogo/templatesApi"
import { useAplicarTemplate } from "@/features/orcamento/orcamentosApi"

const selectClass = cn(
  "flex h-11 w-full min-w-0 rounded-xl border border-input bg-card px-4 py-2 text-base sm:text-sm",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
)

export function AplicarTemplateDialog({
  open,
  onOpenChange,
  projetoId,
  versaoId,
  ambientesExistentes,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  projetoId: string
  versaoId: string
  ambientesExistentes: string[]
}) {
  const templates = useTemplates(open)
  const aplicar = useAplicarTemplate(projetoId, versaoId)

  const [templateId, setTemplateId] = useState("")
  const [ambiente, setAmbiente] = useState("")
  const [area, setArea] = useState("")

  const detalhe = useTemplate(open && templateId ? templateId : null)
  const precisaArea = (detalhe.data?.itens ?? []).some((i) => i.por_area)

  useEffect(() => {
    if (!open) return
    setTemplateId("")
    setAmbiente("")
    setArea("")
  }, [open])

  // pré-preenche a área de referência do template ao escolher (se houver)
  useEffect(() => {
    if (detalhe.data?.area_referencia != null && !area) {
      setArea(String(detalhe.data.area_referencia).replace(".", ","))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detalhe.data?.id])

  const areaNum = area.trim() ? Number(area.replace(",", ".")) || 0 : 0
  const valido =
    templateId.length > 0 && ambiente.trim().length > 0 && (!precisaArea || areaNum > 0)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || aplicar.isPending) return
    try {
      await aplicar.mutateAsync({
        template_id: templateId,
        ambiente_nome: ambiente.trim(),
        area_m2: areaNum > 0 ? areaNum : null,
      })
      toast.success("Cômodo adicionado ao orçamento")
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível aplicar o template.")
    }
  }

  const semTemplates = templates.isSuccess && (templates.data?.length ?? 0) === 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Adicionar cômodo do livro</DialogTitle>
          <DialogDescription>
            Escolha um template, dê um nome ao cômodo e informe a área — geramos as linhas com os custos
            do catálogo. Tudo fica editável depois.
          </DialogDescription>
        </DialogHeader>

        {semTemplates ? (
          <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
            <BookOpen className="mx-auto mb-2 size-5" />
            Nenhum template ainda. Crie um em <strong>Biblioteca → Templates de ambiente</strong> (ou
            salve um cômodo deste orçamento como template).
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <datalist id="aplicar-ambientes">
              {ambientesExistentes.map((a) => (
                <option key={a} value={a} />
              ))}
            </datalist>

            <div className="space-y-1.5">
              <Label htmlFor="ap-tpl">Template</Label>
              <select
                id="ap-tpl"
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
                className={selectClass}
              >
                <option value="">Escolher um template…</option>
                {(templates.data ?? []).map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.tipo} · {t.nivel} ({t.n_itens} {t.n_itens === 1 ? "item" : "itens"})
                  </option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="ap-amb">Nome do cômodo</Label>
                <Input
                  id="ap-amb"
                  list="aplicar-ambientes"
                  value={ambiente}
                  onChange={(e) => setAmbiente(e.target.value)}
                  placeholder="Ex.: Banheiro suíte"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ap-area">Área (m²){precisaArea ? " *" : ""}</Label>
                <Input
                  id="ap-area"
                  inputMode="decimal"
                  value={area}
                  onChange={(e) => setArea(e.target.value)}
                  placeholder="Ex.: 20"
                />
              </div>
            </div>

            {detalhe.data && (
              <div className="max-h-40 space-y-1 overflow-y-auto rounded-xl border border-border bg-card p-3 text-xs">
                {detalhe.data.itens.length === 0 ? (
                  <p className="text-muted-foreground">Este template não tem itens.</p>
                ) : (
                  detalhe.data.itens.map((i) => {
                    // espelha o backend: qtd a 3 casas; subtotal da linha = (soma dos unitários) × qtd
                    // (mesma conta da página, _custo_direto_itens sem majoração).
                    const qtd = i.por_area ? Math.round(i.fator * areaNum * 1000) / 1000 : i.fator
                    const sub = (i.custo_mo + i.custo_material + i.custo_equipamento) * qtd
                    return (
                      <div key={i.id} className="flex justify-between gap-2">
                        <span className="min-w-0 truncate">
                          {i.descricao}
                          <span className="text-muted-foreground">
                            {" "}
                            · {i.por_area ? `${i.fator}/m²` : `${i.fator} ${i.unidade ?? "un"}`}
                          </span>
                        </span>
                        <span className="shrink-0 tabular-nums text-muted-foreground">
                          {formatBRL(sub)}
                        </span>
                      </div>
                    )
                  })
                )}
                {precisaArea && areaNum <= 0 && (
                  <p className="pt-1 text-primary">Informe a área — há itens que escalam por m².</p>
                )}
              </div>
            )}

            <div className="flex gap-2">
              <Button type="button" variant="outline" className="flex-1" onClick={() => onOpenChange(false)}>
                Cancelar
              </Button>
              <Button type="submit" className="flex-1" disabled={!valido || aplicar.isPending}>
                {aplicar.isPending && <Loader2 className="animate-spin" />}
                Adicionar ao orçamento
              </Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
