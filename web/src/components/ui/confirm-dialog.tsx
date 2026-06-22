import { Loader2 } from "lucide-react"
import { useEffect, useState, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

/**
 * Confirmação de ação (poka-yoke: fricção proporcional ao risco). Default = destrutiva (botão
 * vermelho), p/ excluir etapa/item. Para ações CONSTRUTIVAS que ainda merecem confirmação (ex.:
 * "nova versão", "virar obra"), passe variant="default" — não usar o CTA de perigo no positivo.
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Excluir",
  variant = "destructive",
  pending,
  lockSeconds = 0,
  onConfirm,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description?: ReactNode
  confirmLabel?: string
  variant?: "destructive" | "default"
  pending?: boolean
  /** trava temporal: segura o botão confirmar por N segundos (poka-yoke p/ ações muito destrutivas). */
  lockSeconds?: number
  onConfirm: () => void
}) {
  // conta regressiva por tempo decorrido (robusto a throttle de aba); reinicia a cada abertura.
  const [restante, setRestante] = useState(0)
  useEffect(() => {
    if (!open || !lockSeconds) {
      setRestante(0)
      return
    }
    setRestante(lockSeconds)
    const inicio = Date.now()
    const t = setInterval(() => {
      const left = Math.ceil(lockSeconds - (Date.now() - inicio) / 1000)
      setRestante(left > 0 ? left : 0)
      if (left <= 0) clearInterval(t)
    }, 250)
    return () => clearInterval(t)
  }, [open, lockSeconds])
  const travado = restante > 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            className="flex-1"
            onClick={() => onOpenChange(false)}
          >
            Cancelar
          </Button>
          <Button
            type="button"
            variant={variant}
            className="flex-1"
            disabled={pending || travado}
            onClick={onConfirm}
          >
            {pending && <Loader2 className="animate-spin" />}
            {travado ? `Aguarde ${restante}s…` : confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
