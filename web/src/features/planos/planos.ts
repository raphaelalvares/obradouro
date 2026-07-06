import { useQuota } from "@/features/conta/contaApi"

// O backend guarda o CÓDIGO estável do plano ('free' | 'alicerce' | 'pro'); a UI mostra o NOME de
// marca. Fonte única p/ header, paywall e Configurações não divergirem.
export const PLAN_LABELS: Record<string, string> = {
  free: "Canteiro",
  alicerce: "Alicerce",
  pro: "Mestre",
}

export function planoLabel(codigo: string | null | undefined): string {
  if (!codigo) return "—"
  return PLAN_LABELS[codigo] ?? codigo.charAt(0).toUpperCase() + codigo.slice(1)
}

// Em qual plano cada eixo premium passa a existir — usado nas mensagens de upsell (código do plano).
export const EIXO_PLANO: Record<string, string> = {
  export_pdf: "alicerce",
  logo: "alicerce",
  obras_ativas: "alicerce",
  armazenamento: "alicerce",
  portal: "pro",
  chat: "pro",
}

/** Conveniência sobre `/me/quota`: plano + flags + capacidade, sem estourar erro enquanto carrega.
 * Otimista até o fetch chegar (não trava botão à toa). */
export function usePlano() {
  const q = useQuota()
  const data = q.data
  const flags = data?.flags ?? {}
  const plano = data?.plano ?? "free"
  return {
    quota: data,
    isLoading: q.isLoading,
    plano,
    label: planoLabel(plano),
    isFree: plano === "free",
    isPro: plano === "pro",
    /** true se a flag do plano está ligada; false enquanto carrega (não vaza recurso premium). */
    flag: (name: string) => flags[name] === true,
    podeCriarObra: data?.pode_criar_obra ?? true,
  }
}
