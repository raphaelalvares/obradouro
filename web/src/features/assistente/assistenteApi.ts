import { useMutation } from "@tanstack/react-query"

import { api } from "@/lib/api"

export interface MensagemChat {
  papel: "user" | "assistant"
  conteudo: string
}

export interface AssistenteResposta {
  resposta: string
  disponivel: boolean
  pendencias_count: number
}

export function useAssistente() {
  return useMutation({
    mutationFn: (v: { mensagem: string; historico: MensagemChat[] }) =>
      api.post<AssistenteResposta>("/api/v1/assistente", v),
  })
}
