import { Bot, Send, X } from "lucide-react"
import { useRef, useState, type FormEvent } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { ApiError } from "@/lib/api"
import { useAssistente, type MensagemChat } from "@/features/assistente/assistenteApi"

/** Assistente conversacional (botão flutuante + painel). Conhece o comercial do usuário; quando o
 * Ollama está desligado, responde o fallback determinístico (lista das pendências). */
export function AssistenteChat() {
  const [aberto, setAberto] = useState(false)
  const [msgs, setMsgs] = useState<MensagemChat[]>([])
  const [texto, setTexto] = useState("")
  const enviar = useAssistente()
  const fimRef = useRef<HTMLDivElement>(null)

  async function onEnviar(e: FormEvent) {
    e.preventDefault()
    const pergunta = texto.trim()
    if (!pergunta || enviar.isPending) return
    const historico = msgs
    setMsgs((m) => [...m, { papel: "user", conteudo: pergunta }])
    setTexto("")
    try {
      const r = await enviar.mutateAsync({ mensagem: pergunta, historico })
      setMsgs((m) => [...m, { papel: "assistant", conteudo: r.resposta }])
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Falha ao falar com o assistente."
      setMsgs((m) => [...m, { papel: "assistant", conteudo: msg }])
    } finally {
      requestAnimationFrame(() => fimRef.current?.scrollIntoView({ behavior: "smooth" }))
    }
  }

  if (!aberto) {
    return (
      <Button
        onClick={() => setAberto(true)}
        size="icon"
        aria-label="Abrir assistente"
        className="fixed bottom-5 right-5 z-40 size-12 rounded-full shadow-lg"
      >
        <Bot className="size-5" />
      </Button>
    )
  }

  return (
    <div className="fixed bottom-5 right-5 z-40 flex h-[32rem] max-h-[calc(100dvh-2.5rem)] w-[22rem] max-w-[calc(100vw-2.5rem)] flex-col rounded-2xl border border-border bg-card shadow-2xl">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="flex items-center gap-2 text-sm font-medium">
          <Bot className="size-4 text-primary" />
          Assistente
        </span>
        <button
          type="button"
          onClick={() => setAberto(false)}
          aria-label="Fechar"
          className="text-muted-foreground transition-colors hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {msgs.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Pergunte sobre o seu comercial — ex.: <em>“o que está pendente?”</em> ou{" "}
            <em>“quanto tenho em negociação?”</em>
          </p>
        )}
        {msgs.map((m, i) => (
          <div
            key={i}
            className={cn(
              "max-w-[85%] whitespace-pre-wrap break-words rounded-xl px-3 py-2 text-sm",
              m.papel === "user"
                ? "ml-auto bg-primary/15 text-foreground"
                : "mr-auto bg-muted text-foreground",
            )}
          >
            {m.conteudo}
          </div>
        ))}
        {enviar.isPending && (
          <div className="mr-auto rounded-xl bg-muted px-3 py-2 text-sm text-muted-foreground">
            digitando…
          </div>
        )}
        <div ref={fimRef} />
      </div>

      <form onSubmit={onEnviar} className="flex items-center gap-2 border-t border-border p-3">
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Pergunte algo…"
          className="h-10 min-w-0 flex-1 rounded-xl border border-input bg-card px-3 text-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:text-sm"
        />
        <Button
          type="submit"
          size="icon"
          disabled={!texto.trim() || enviar.isPending}
          aria-label="Enviar"
        >
          <Send className="size-4" />
        </Button>
      </form>
    </div>
  )
}
