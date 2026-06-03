import { FileUp, Loader2 } from "lucide-react"
import { useRef } from "react"
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
import { useImportarNfe } from "@/features/estoque/estoqueApi"

export function ImportNfeDialog({
  obraId,
  open,
  onOpenChange,
}: {
  obraId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const importar = useImportarNfe(obraId)
  const fileRef = useRef<HTMLInputElement>(null)

  function close(o: boolean) {
    onOpenChange(o)
  }

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = "" // permite re-selecionar o mesmo arquivo
    if (!file) return
    try {
      const r = await importar.mutateAsync(file)
      if (!r.criada) {
        toast.info("Esta nota já tinha sido importada (nada duplicado).")
      } else {
        toast.success(`Nota importada — ${r.itens_novos} ${r.itens_novos === 1 ? "item" : "itens"}.`)
      }
      close(false)
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        toast.error(err.message || "Arquivo não parece uma NF-e válida.")
      } else if (err instanceof ApiError && err.status === 413) {
        toast.error("Arquivo grande demais.")
      } else {
        toast.error(err instanceof ApiError ? err.message : "Não foi possível importar a nota.")
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Importar NF-e</DialogTitle>
          <DialogDescription>
            Selecione o <strong>XML</strong> da nota fiscal. Reimportar a mesma nota não duplica o
            estoque.
          </DialogDescription>
        </DialogHeader>

        <input
          ref={fileRef}
          type="file"
          accept=".xml,text/xml,application/xml"
          className="hidden"
          onChange={onPick}
        />
        <Button
          type="button"
          className="w-full"
          disabled={importar.isPending}
          onClick={() => fileRef.current?.click()}
        >
          {importar.isPending ? <Loader2 className="animate-spin" /> : <FileUp />}
          {importar.isPending ? "Importando…" : "Escolher arquivo XML"}
        </Button>
      </DialogContent>
    </Dialog>
  )
}
