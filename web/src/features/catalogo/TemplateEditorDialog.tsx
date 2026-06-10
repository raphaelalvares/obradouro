import { Loader2, Plus, Trash2 } from "lucide-react"
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
import { useCatalogo } from "@/features/catalogo/catalogoApi"
import {
  useAddTemplateItem,
  useAtualizarTemplate,
  useCriarTemplate,
  useDelTemplateItem,
  useEditTemplateItem,
  useTemplate,
  type TemplateItem,
} from "@/features/catalogo/templatesApi"

const selectClass = cn(
  "flex h-11 w-full min-w-0 rounded-xl border border-input bg-card px-4 py-2 text-base sm:text-sm",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
)

export function TemplateEditorDialog({
  open,
  onOpenChange,
  templateId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** null = criar novo; depois de criado, vira edição */
  templateId: string | null
}) {
  const [id, setId] = useState<string | null>(templateId)
  useEffect(() => {
    if (open) setId(templateId)
  }, [open, templateId])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{id ? "Editar template" : "Novo template de ambiente"}</DialogTitle>
          <DialogDescription>
            Uma receita por tipo × nível (ex.: Banheiro · alto padrão) com serviços do catálogo. Marque
            os que escalam por m² (área) — o resto é quantidade fixa.
          </DialogDescription>
        </DialogHeader>
        {id ? (
          <Editor id={id} onClose={() => onOpenChange(false)} />
        ) : (
          <Criar onCriado={setId} onCancel={() => onOpenChange(false)} />
        )}
      </DialogContent>
    </Dialog>
  )
}

function Criar({ onCriado, onCancel }: { onCriado: (id: string) => void; onCancel: () => void }) {
  const criar = useCriarTemplate()
  const [tipo, setTipo] = useState("")
  const [nivel, setNivel] = useState("")
  const [area, setArea] = useState("")
  const valido = tipo.trim().length > 0 && nivel.trim().length > 0

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || criar.isPending) return
    try {
      const t = await criar.mutateAsync({
        tipo: tipo.trim(),
        nivel: nivel.trim(),
        area_referencia: area.trim() ? Number(area.replace(",", ".")) || null : null,
      })
      onCriado(t.id) // segue p/ adicionar os serviços
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast.error("Já existe um template com esse tipo e nível.")
      } else {
        toast.error(err instanceof ApiError ? err.message : "Não foi possível criar.")
      }
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="te-tipo">Tipo *</Label>
          <Input id="te-tipo" value={tipo} onChange={(e) => setTipo(e.target.value)} placeholder="Ex.: Banheiro" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="te-nivel">Nível *</Label>
          <Input id="te-nivel" value={nivel} onChange={(e) => setNivel(e.target.value)} placeholder="Ex.: Alto padrão" />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="te-area">Área de referência (m²)</Label>
        <Input id="te-area" inputMode="decimal" value={area} onChange={(e) => setArea(e.target.value)} placeholder="Opcional — ex.: 20" />
      </div>
      <div className="flex gap-2">
        <Button type="button" variant="outline" className="flex-1" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" className="flex-1" disabled={!valido || criar.isPending}>
          {criar.isPending && <Loader2 className="animate-spin" />}
          Criar e adicionar serviços
        </Button>
      </div>
    </form>
  )
}

function Editor({ id, onClose }: { id: string; onClose: () => void }) {
  const tpl = useTemplate(id)
  const catalogo = useCatalogo(true)
  const atualizar = useAtualizarTemplate()
  const addItem = useAddTemplateItem(id)

  const [tipo, setTipo] = useState("")
  const [nivel, setNivel] = useState("")
  const [area, setArea] = useState("")
  const [novoServico, setNovoServico] = useState("")

  useEffect(() => {
    if (!tpl.data) return
    setTipo(tpl.data.tipo)
    setNivel(tpl.data.nivel)
    setArea(tpl.data.area_referencia != null ? String(tpl.data.area_referencia).replace(".", ",") : "")
  }, [tpl.data?.id])

  function salvarCabecalho(patch: { tipo?: string; nivel?: string; area_referencia?: number | null }) {
    void atualizar.mutateAsync({ id, patch }).catch((err) => {
      if (err instanceof ApiError && err.status === 409) toast.error("Já existe um template com esse tipo e nível.")
      else toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar.")
    })
  }

  async function adicionarServico() {
    if (!novoServico) return
    const ordem = tpl.data?.itens.length ?? 0
    try {
      await addItem.mutateAsync({ servico_id: novoServico, por_area: false, fator: 1, ordem })
      setNovoServico("")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível adicionar.")
    }
  }

  // serviços ainda não usados no template (evita duplicar)
  const usados = new Set((tpl.data?.itens ?? []).map((i) => i.servico_id))
  const disponiveis = (catalogo.data ?? []).filter((s) => !usados.has(s.id))

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="ed-tipo">Tipo</Label>
          <Input
            id="ed-tipo"
            value={tipo}
            onChange={(e) => setTipo(e.target.value)}
            onBlur={() => tipo.trim() && tipo.trim() !== tpl.data?.tipo && salvarCabecalho({ tipo: tipo.trim() })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ed-nivel">Nível</Label>
          <Input
            id="ed-nivel"
            value={nivel}
            onChange={(e) => setNivel(e.target.value)}
            onBlur={() => nivel.trim() && nivel.trim() !== tpl.data?.nivel && salvarCabecalho({ nivel: nivel.trim() })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ed-area">Área ref. (m²)</Label>
          <Input
            id="ed-area"
            inputMode="decimal"
            value={area}
            onChange={(e) => setArea(e.target.value)}
            onBlur={() => salvarCabecalho({ area_referencia: area.trim() ? Number(area.replace(",", ".")) || null : null })}
          />
        </div>
      </div>

      <div className="space-y-2">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Serviços</div>
        {tpl.isLoading ? (
          <div className="py-6 text-center"><Loader2 className="mx-auto animate-spin text-muted-foreground" /></div>
        ) : (tpl.data?.itens.length ?? 0) === 0 ? (
          <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
            Nenhum serviço ainda. Adicione abaixo (do catálogo).
          </p>
        ) : (
          <ul className="max-h-[40vh] space-y-2 overflow-y-auto">
            {tpl.data!.itens.map((it) => (
              <ItemRow key={it.id} templateId={id} item={it} />
            ))}
          </ul>
        )}
      </div>

      {/* adicionar serviço do catálogo */}
      <div className="flex gap-2">
        <select
          value={novoServico}
          onChange={(e) => setNovoServico(e.target.value)}
          className={selectClass}
        >
          <option value="">Adicionar serviço do catálogo…</option>
          {disponiveis.map((s) => (
            <option key={s.id} value={s.id}>
              {s.descricao}
              {s.unidade ? ` (${s.unidade})` : ""}
            </option>
          ))}
        </select>
        <Button type="button" variant="outline" className="shrink-0" disabled={!novoServico || addItem.isPending} onClick={adicionarServico}>
          {addItem.isPending ? <Loader2 className="animate-spin" /> : <Plus />}
        </Button>
      </div>
      {catalogo.isSuccess && (catalogo.data?.length ?? 0) === 0 && (
        <p className="text-xs text-muted-foreground">
          Catálogo vazio — cadastre serviços na aba <strong>Serviços</strong> primeiro.
        </p>
      )}

      <Button type="button" className="w-full" onClick={onClose}>
        Concluir
      </Button>
    </div>
  )
}

function ItemRow({ templateId, item }: { templateId: string; item: TemplateItem }) {
  const editar = useEditTemplateItem(templateId)
  const excluir = useDelTemplateItem(templateId)
  const [fator, setFator] = useState(String(item.fator).replace(".", ","))
  const [etapa, setEtapa] = useState(item.etapa ?? "")

  useEffect(() => {
    setFator(String(item.fator).replace(".", ","))
    setEtapa(item.etapa ?? "")
  }, [item.fator, item.etapa])

  function patch(p: { por_area?: boolean; fator?: number; etapa?: string | null }) {
    void editar.mutateAsync({ itemId: item.id, patch: p }).catch((err) => {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar.")
    })
  }

  return (
    <li className="rounded-xl border border-border bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 flex-1 break-words text-sm font-medium">{item.descricao}</p>
        <button
          type="button"
          aria-label="Remover do template"
          className="shrink-0 rounded-md p-1 text-muted-foreground hover:text-destructive"
          onClick={() => void excluir.mutateAsync(item.id)}
        >
          <Trash2 className="size-3.5" />
        </button>
      </div>
      <div className="mt-2 flex flex-wrap items-end gap-3">
        <label className="flex items-center gap-1.5 text-xs">
          <input
            type="checkbox"
            checked={item.por_area}
            onChange={(e) => patch({ por_area: e.target.checked })}
            className="size-4 accent-primary"
          />
          escala por m²
        </label>
        <div className="space-y-1">
          <span className="block text-[10px] uppercase text-muted-foreground">
            {item.por_area ? "coef. por m²" : `quantidade (${item.unidade ?? "un"})`}
          </span>
          <Input
            className="h-9 w-28"
            inputMode="decimal"
            value={fator}
            onChange={(e) => setFator(e.target.value)}
            onBlur={() => {
              const n = Number(fator.replace(",", ".")) || 0
              if (n !== item.fator) patch({ fator: n })
            }}
          />
        </div>
        <div className="min-w-[8rem] flex-1 space-y-1">
          <span className="block text-[10px] uppercase text-muted-foreground">etapa (opcional)</span>
          <Input
            className="h-9"
            value={etapa}
            onChange={(e) => setEtapa(e.target.value)}
            onBlur={() => {
              const val = etapa.trim() || null
              if (val !== (item.etapa ?? null)) patch({ etapa: val })
            }}
            placeholder="Ex.: Revestimentos"
          />
        </div>
      </div>
    </li>
  )
}
