import { Loader2, type LucideIcon } from "lucide-react"
import type { ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

/** Spinner centralizado (loading de página/seção). */
export function CenteredSpinner({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center justify-center py-16 text-muted-foreground", className)}>
      <Loader2 className="size-6 animate-spin" />
    </div>
  )
}

/** Estado vazio — guia o usuário ao próximo passo (poka-yoke: nunca uma tela morta). */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="flex animate-fade-up flex-col items-center justify-center rounded-2xl border border-dashed border-border px-6 py-16 text-center">
      <div className="mb-4 flex size-14 items-center justify-center rounded-full bg-accent text-primary">
        <Icon className="size-6" />
      </div>
      <h3 className="font-word text-xl">{title}</h3>
      {description && (
        <p className="mt-1 max-w-xs text-sm text-muted-foreground">{description}</p>
      )}
      {action && <div className="mt-6">{action}</div>}
    </div>
  )
}

/** Estado de erro com ação de tentar de novo. */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-destructive/40 bg-destructive/5 px-6 py-12 text-center">
      <p className="text-sm text-foreground">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          Tentar de novo
        </Button>
      )}
    </div>
  )
}
