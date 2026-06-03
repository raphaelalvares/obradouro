import { cn } from "@/lib/utils"

/**
 * Wordmark CRIA em texto (Oswald). Placeholder editorial até entrar o logo oficial (.svg/.png),
 * que depois troca só aqui. O ponto âmbar é o acento da marca.
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("font-display font-light tracking-[0.3em] text-foreground", className)}>
      CRIA<span className="text-primary">.</span>
    </span>
  )
}
