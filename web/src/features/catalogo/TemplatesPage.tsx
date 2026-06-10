import { LayoutTemplate, Pencil, Plus, Trash2 } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { ApiError } from "@/lib/api"
import { TemplateEditorDialog } from "@/features/catalogo/TemplateEditorDialog"
import {
  useExcluirTemplate,
  useTemplates,
  type TemplateResumo,
} from "@/features/catalogo/templatesApi"

export function TemplatesPage() {
  const templates = useTemplates()
  const excluir = useExcluirTemplate()
  const [editor, setEditor] = useState<{ id: string | null } | null>(null)
  const [excluindo, setExcluindo] = useState<TemplateResumo | null>(null)

  async function onExcluir() {
    if (!excluindo) return
    try {
      await excluir.mutateAsync(excluindo.id)
      setExcluindo(null)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível excluir.")
    }
  }

  const lista = templates.data ?? []

  return (
    <div>
      <div className="mb-4 flex items-start justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Receitas por <strong>tipo × nível</strong>. Aplique a um cômodo no orçamento para gerar as
          linhas já com os custos do catálogo.
        </p>
        <Button className="shrink-0" onClick={() => setEditor({ id: null })}>
          <Plus />
          Novo template
        </Button>
      </div>

      {templates.isLoading && <CenteredSpinner />}
      {templates.isError && (
        <ErrorState message="Não foi possível carregar os templates." onRetry={() => void templates.refetch()} />
      )}

      {templates.isSuccess && lista.length === 0 && (
        <EmptyState
          icon={LayoutTemplate}
          title="Nenhum template ainda"
          description="Monte um template aqui, ou salve um cômodo de um orçamento real como template."
          action={
            <Button onClick={() => setEditor({ id: null })}>
              <Plus />
              Novo template
            </Button>
          }
        />
      )}

      {lista.length > 0 && (
        <ul className="space-y-2">
          {lista.map((t) => (
            <li
              key={t.id}
              className="flex items-center gap-2 rounded-2xl border border-border bg-card px-4 py-3"
            >
              <button
                type="button"
                className="min-w-0 flex-1 text-left"
                onClick={() => setEditor({ id: t.id })}
              >
                <p className="break-words text-sm font-medium">
                  {t.tipo} <span className="text-muted-foreground">· {t.nivel}</span>
                </p>
                <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                  <span>{t.n_itens} {t.n_itens === 1 ? "serviço" : "serviços"}</span>
                  {t.area_referencia != null && (
                    <span>ref. {String(t.area_referencia).replace(".", ",")} m²</span>
                  )}
                </div>
              </button>
              <button
                type="button"
                aria-label="Editar"
                className="shrink-0 rounded-md p-1 text-muted-foreground hover:text-foreground"
                onClick={() => setEditor({ id: t.id })}
              >
                <Pencil className="size-3.5" />
              </button>
              <button
                type="button"
                aria-label="Excluir"
                className="shrink-0 rounded-md p-1 text-muted-foreground hover:text-destructive"
                onClick={() => setExcluindo(t)}
              >
                <Trash2 className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <TemplateEditorDialog
        open={editor !== null}
        onOpenChange={(o) => {
          if (!o) setEditor(null)
        }}
        templateId={editor?.id ?? null}
      />
      <ConfirmDialog
        open={excluindo !== null}
        onOpenChange={(o) => {
          if (!o) setExcluindo(null)
        }}
        title="Excluir template"
        description={excluindo ? `Remover o template "${excluindo.tipo} · ${excluindo.nivel}"?` : ""}
        pending={excluir.isPending}
        onConfirm={onExcluir}
      />
    </div>
  )
}
