/** Add-on de armazenamento: tamanhos de bloco + helpers. Compartilhado entre o Financeiro do
 * assinante (contrata via Stripe) e o painel admin (cortesia). O PREÇO mora no backend
 * (STRIPE_PRICE_ARMAZENAMENTO / ARMAZENAMENTO_PRECO_GB_CENTAVOS) e chega via /me/financeiro e
 * /admin/armazenamento — aqui só ficam os tamanhos e a formatação. */

/** Blocos oferecidos, em GB (somam ao total contratado). */
export const BLOCOS_GB = [10, 50, 100, 250, 500, 1024] as const

/** Rótulo curto: 500 → "500 GB", 1024 → "1 TB". */
export function labelGb(gb: number): string {
  return gb >= 1024 ? `${gb / 1024} TB` : `${gb} GB`
}

/** Preço mensal (centavos) de `gb` a um preço/GB (centavos). */
export function precoMensalCents(gb: number, precoGbCentavos: number): number {
  return gb * precoGbCentavos
}
