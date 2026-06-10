import { ChevronDown } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { cn } from "@/lib/utils"

const inputClass = cn(
  "flex h-11 w-full min-w-0 rounded-xl border border-input bg-card pl-4 pr-10 py-2 text-base sm:text-sm",
  "placeholder:text-muted-foreground",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
)

/**
 * Combobox: input de texto LIVRE + dropdown clicável com as opções (ex.: cômodos do banco).
 * Mais confiável que o <datalist> nativo (que não abre no clique e filtra pelo valor atual).
 * O usuário pode escolher uma opção OU digitar uma nova — o backend resolve/cria.
 *
 * Notas de implementação (vive dentro de modal Radix):
 * - abre por clique/digitação/ArrowDown — NÃO no foco (senão o auto-focus do Radix abriria sozinho);
 * - Esc com a lista aberta fecha só a lista (stopPropagation p/ o Radix não fechar o dialog);
 * - sem Portal de propósito: portar p/ o body faria o Radix tratar o clique na opção como
 *   "fora do dialog" e fechá-lo. Em vez disso, abre p/ CIMA quando há pouco espaço abaixo.
 */
export function Combobox({
  value,
  onChange,
  options,
  placeholder,
  id,
  maxLength,
  emptyHint = "Nenhuma opção cadastrada",
}: {
  value: string
  onChange: (v: string) => void
  options: string[]
  placeholder?: string
  id?: string
  maxLength?: number
  emptyHint?: string
}) {
  const [open, setOpen] = useState(false)
  const [dropUp, setDropUp] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  function abrir() {
    const r = wrapRef.current?.getBoundingClientRect()
    // abre p/ cima se há pouco espaço abaixo e mais espaço acima (evita corte no rodapé do modal).
    if (r) setDropUp(window.innerHeight - r.bottom < 240 && r.top > 240)
    setOpen(true)
  }

  useEffect(() => {
    if (!open) return
    function onDoc(e: MouseEvent) {
      // a lista fica DENTRO do wrapRef → clicar numa opção não cai aqui (não fecha antes do onClick).
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onDoc)
    return () => document.removeEventListener("mousedown", onDoc)
  }, [open])

  const q = value.trim().toLowerCase()
  // filtra só quando o texto NÃO bate exatamente uma opção (assim, ao reabrir num valor escolhido,
  // a lista mostra tudo em vez de só o item atual — a dor do datalist).
  const exato = options.some((o) => o.toLowerCase() === q)
  const filtradas = q && !exato ? options.filter((o) => o.toLowerCase().includes(q)) : options

  return (
    <div ref={wrapRef} className="relative">
      <input
        id={id}
        type="text"
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          abrir()
        }}
        onClick={abrir}
        onKeyDown={(e) => {
          if (e.key === "Escape" && open) {
            e.preventDefault()
            e.stopPropagation() // fecha só a lista, não o dialog Radix
            setOpen(false)
          } else if (e.key === "ArrowDown" && !open) {
            e.preventDefault()
            abrir()
          }
        }}
        maxLength={maxLength}
        placeholder={placeholder}
        autoComplete="off"
        className={inputClass}
      />
      <button
        type="button"
        tabIndex={-1}
        aria-label="Abrir lista"
        onClick={() => (open ? setOpen(false) : abrir())}
        className="absolute right-2 top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground hover:text-foreground"
      >
        <ChevronDown className="size-4" />
      </button>

      {open && (
        <ul
          className={cn(
            "absolute z-50 max-h-56 w-full overflow-auto rounded-xl border border-border bg-card py-1 shadow-xl",
            dropUp ? "bottom-full mb-1" : "top-full mt-1",
          )}
        >
          {options.length === 0 ? (
            <li className="px-3 py-2 text-sm text-muted-foreground">{emptyHint}</li>
          ) : filtradas.length === 0 ? (
            <li className="px-3 py-2 text-sm text-muted-foreground">
              Nada encontrado — mantém “{value.trim()}”.
            </li>
          ) : (
            filtradas.map((o) => (
              <li key={o}>
                <button
                  type="button"
                  onClick={() => {
                    onChange(o)
                    setOpen(false)
                  }}
                  className={cn(
                    "block w-full px-3 py-2 text-left text-sm hover:bg-accent",
                    o.toLowerCase() === q && "bg-accent/60",
                  )}
                >
                  {o}
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  )
}
