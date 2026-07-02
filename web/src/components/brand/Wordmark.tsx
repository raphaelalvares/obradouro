import { cn } from "@/lib/utils"
import { LogoMark } from "@/components/brand/Logo"

/**
 * Lockup da marca Obra D'Ouro: símbolo (tijolos + raio, ouro #D4AF37) + nome nominativo em
 * Rajdhani (bold, caixa alta — manual de identidade). É o ponto ÚNICO da marca: trocar aqui
 * reflete no header, login, portal e páginas legais. O tamanho acompanha a fonte definida via
 * `className` (ex.: text-lg / text-4xl); o símbolo dimensiona em `em`. Como é `inline-flex`,
 * centraliza sozinho dentro de um container `text-center` (heros de login/cadastro).
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 whitespace-nowrap text-foreground",
        className,
      )}
    >
      <LogoMark className="h-[1.35em] w-auto shrink-0" />
      <span className="font-display font-bold uppercase tracking-[0.12em] leading-none">
        Obra D&apos;Ouro
      </span>
    </span>
  )
}
