import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"

export type Severidade = "alta" | "media" | "baixa"

/** Apontamento do agente (espelha ApontamentoOut do backend). `mensagem` é a humanizada (3B) ou a
 * baseline da regra; `humanizado` diz qual. */
export interface Apontamento {
  id_oportunidade: string
  seq_humano: number | null
  nome: string
  regra_id: string
  categoria: string
  severidade: Severidade
  etapa: string
  contato_telefone: string | null
  contato_email: string | null
  dias: number | null
  titulo: string
  mensagem: string
  sugestao: string | null
  humanizado: boolean
}

export function useLembretes() {
  return useQuery({
    queryKey: ["lembretes"],
    queryFn: () => api.get<Apontamento[]>("/api/v1/lembretes"),
    // read-only e (com o 3B ligado) custoso → segura 5 min antes de refazer.
    staleTime: 5 * 60_000,
  })
}

export const SEV_META: Record<Severidade, { label: string; cor: string }> = {
  alta: { label: "Alta", cor: "#E5654B" },
  media: { label: "Média", cor: "#D8A53A" },
  baixa: { label: "Baixa", cor: "#938C7E" },
}
