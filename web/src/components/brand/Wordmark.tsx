import { cn } from "@/lib/utils"

/**
 * Lockup da marca Obra D'Ouro: símbolo oficial (tijolos + raio, cobre metálico — extraído do
 * render em web/public/brand/obradouro-mark.png, fundo transparente) + nome nominativo em Rajdhani
 * (bold, caixa alta — manual de identidade). Ponto ÚNICO da marca: trocar aqui reflete no header,
 * login, portal e páginas legais. O tamanho acompanha a fonte via `className` (ex.: text-lg /
 * text-4xl); o símbolo dimensiona em `em`. Como é `inline-flex`, centraliza sozinho dentro de um
 * container `text-center` (heros de login/cadastro).
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 whitespace-nowrap text-foreground",
        className,
      )}
    >
      <img
        src="/brand/obradouro-mark.png"
        alt=""
        aria-hidden="true"
        draggable={false}
        className="h-[1.5em] w-auto shrink-0 select-none"
      />
      <span className="font-wordmark font-semibold uppercase tracking-[0.14em] leading-none">
        Obra D&apos;Ouro
      </span>
    </span>
  )
}
