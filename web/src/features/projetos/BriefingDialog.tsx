import { Loader2 } from "lucide-react"
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
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { ApiError } from "@/lib/api"
import { useAtualizarProjeto, useProjeto, type Briefing } from "@/features/projetos/projetosApi"

/** Campos fixos do onboarding (o backend guarda como dict livre). */
const CAMPOS: { key: string; label: string; multiline?: boolean; placeholder?: string }[] = [
  { key: "objetivo", label: "Objetivo do projeto", multiline: true, placeholder: "O que o cliente quer alcançar" },
  { key: "estilo", label: "Estilo e referências", multiline: true, placeholder: "Linguagem visual, materiais, inspirações" },
  { key: "escopo", label: "Ambientes / escopo", multiline: true, placeholder: "O que entra no projeto" },
  { key: "prazo", label: "Prazo desejado", placeholder: "Ex.: 3 meses" },
  { key: "orcamento", label: "Orçamento estimado", placeholder: "Ex.: R$ 80.000" },
  { key: "observacoes", label: "Observações", multiline: true },
]

export function BriefingDialog({
  projetoId,
  open,
  onOpenChange,
  podeEditar,
}: {
  projetoId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  podeEditar: boolean
}) {
  const projeto = useProjeto(projetoId)
  const salvar = useAtualizarProjeto(projetoId)
  const [form, setForm] = useState<Briefing>({})

  // recarrega o form a partir do briefing salvo sempre que abrir
  useEffect(() => {
    if (open) setForm({ ...(projeto.data?.briefing ?? {}) })
  }, [open, projeto.data?.briefing])

  function set(key: string, value: string) {
    setForm((f) => ({ ...f, [key]: value }))
  }

  async function onSalvar() {
    if (salvar.isPending) return
    // remove vazios p/ não poluir o dict
    const briefing: Briefing = {}
    for (const { key } of CAMPOS) {
      const v = (form[key] ?? "").trim()
      if (v) briefing[key] = v
    }
    try {
      await salvar.mutateAsync({ briefing })
      toast.success("Briefing salvo")
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar o briefing.")
    }
  }

  const vazio = !podeEditar && CAMPOS.every(({ key }) => !(projeto.data?.briefing?.[key] ?? "").trim())

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Onboarding</DialogTitle>
          <DialogDescription>
            {podeEditar ? "O briefing que guia o projeto." : "Briefing definido pelo arquiteto."}
          </DialogDescription>
        </DialogHeader>

        {vazio ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            O arquiteto ainda não preencheu o briefing.
          </p>
        ) : (
          <div className="space-y-4">
            {CAMPOS.map(({ key, label, multiline, placeholder }) => {
              const val = form[key] ?? ""
              if (!podeEditar) {
                const saved = (projeto.data?.briefing?.[key] ?? "").trim()
                if (!saved) return null
                return (
                  <div key={key} className="space-y-1">
                    <Label>{label}</Label>
                    <p className="whitespace-pre-wrap text-sm">{saved}</p>
                  </div>
                )
              }
              return (
                <div key={key} className="space-y-1.5">
                  <Label htmlFor={`bf-${key}`}>{label}</Label>
                  {multiline ? (
                    <Textarea
                      id={`bf-${key}`}
                      value={val}
                      placeholder={placeholder}
                      onChange={(e) => set(key, e.target.value)}
                    />
                  ) : (
                    <Input
                      id={`bf-${key}`}
                      value={val}
                      placeholder={placeholder}
                      onChange={(e) => set(key, e.target.value)}
                    />
                  )}
                </div>
              )
            })}
          </div>
        )}

        {podeEditar && (
          <Button className="w-full" disabled={salvar.isPending} onClick={onSalvar}>
            {salvar.isPending && <Loader2 className="animate-spin" />}
            Salvar briefing
          </Button>
        )}
      </DialogContent>
    </Dialog>
  )
}
