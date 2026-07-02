import type { SVGProps } from "react"

/**
 * Símbolo da marca Obra D'Ouro: tijolos (base sólida) + raio (energia/tecnologia), em ouro
 * metálico #D4AF37 — conforme o manual de identidade. O "recorte" do raio usa a cor de fundo
 * (`--background`, preto no dark-first), então o símbolo assenta bem sobre o header/cards.
 * viewBox recortado ao desenho (sem o texto do logo original, que aqui é composto em HTML/Rajdhani).
 */
export function LogoMark({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="30 20 140 155"
      fill="none"
      role="img"
      aria-hidden="true"
      className={className}
      {...props}
    >
      <g fill="#D4AF37">
        <rect x="35" y="115" width="50" height="20" rx="2" />
        <rect x="90" y="115" width="75" height="20" rx="2" />
        <rect x="55" y="90" width="60" height="20" rx="2" />
        <rect x="120" y="90" width="45" height="20" rx="2" />
        <rect x="75" y="65" width="65" height="20" rx="2" />
      </g>
      <polygon
        points="105,25 60,110 95,110 75,170 145,90 100,90"
        fill="#D4AF37"
        stroke="hsl(var(--background))"
        strokeWidth="6"
        strokeLinejoin="round"
      />
    </svg>
  )
}
