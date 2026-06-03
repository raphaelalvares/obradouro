import { FileSpreadsheet, Loader2, UploadCloud } from "lucide-react"
import { useRef, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ApiError } from "@/lib/api"
import { useImportarChecklist } from "@/features/checklist/checklistApi"

export function ImportarChecklistDialog({
  obraId,
  open,
  onOpenChange,
}: {
  obraId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [arquivo, setArquivo] = useState<File | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const importar = useImportarChecklist(obraId)

  function close(o: boolean) {
    if (!o) setArquivo(null)
    onOpenChange(o)
  }

  async function onImportar() {
    if (!arquivo || importar.isPending) return
    try {
      const r = await importar.mutateAsync(arquivo)
      toast.success("Checklist importado", {
        description: `${r.etapas_novas} etapa(s) e ${r.itens_novos} item(ns) novos · ${r.etapas_existentes + r.itens_existentes} já existiam.`,
      })
      close(false)
    } catch (err) {
      // 422 = template fora do padrão (com o nº da linha quando for item sem etapa)
      toast.error(err instanceof ApiError ? err.message : "Falha ao importar o template.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Importar checklist</DialogTitle>
          <DialogDescription>
            Use sua <strong>planilha de orçamento</strong> (.xlsx) — as etapas e serviços viram o
            checklist, já com unidade/quantidade/valores. Também aceita o template simples{" "}
            <code>etapa · item</code>. Reimportar o mesmo arquivo não duplica.
          </DialogDescription>
        </DialogHeader>

        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-card px-6 py-8 text-center transition-colors hover:border-primary/50"
        >
          {arquivo ? (
            <>
              <FileSpreadsheet className="size-7 text-primary" />
              <span className="text-sm font-medium">{arquivo.name}</span>
              <span className="text-xs text-muted-foreground">tocar para trocar</span>
            </>
          ) : (
            <>
              <UploadCloud className="size-7 text-muted-foreground" />
              <span className="text-sm">Escolher arquivo .xlsx</span>
            </>
          )}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          className="hidden"
          onChange={(e) => setArquivo(e.target.files?.[0] ?? null)}
        />

        <div className="flex gap-2">
          <Button type="button" variant="outline" className="flex-1" onClick={() => close(false)}>
            Cancelar
          </Button>
          <Button
            type="button"
            className="flex-1"
            disabled={!arquivo || importar.isPending}
            onClick={onImportar}
          >
            {importar.isPending && <Loader2 className="animate-spin" />}
            Importar
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
