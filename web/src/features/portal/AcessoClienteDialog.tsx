import { Clock, Copy, Link2, Loader2, Mail, Trash2 } from "lucide-react"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { CenteredSpinner } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import {
  portalCadastroUrl,
  useAcessos,
  useAutorizarAcesso,
  useDefinirPrazo,
  useRevogarAcesso,
  type AcessoAlvo,
  type AcessoCliente,
  type ValidadeTipo,
} from "@/features/portal/portalApi"

async function copiar(texto: string, msg: string) {
  try {
    await navigator.clipboard.writeText(texto)
    toast.success(msg)
  } catch {
    toast.error("Não consegui copiar — copie manualmente.")
  }
}

function hojeISO(): string {
  return new Date().toLocaleDateString("en-CA") // YYYY-MM-DD local
}

function fmtData(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("pt-BR")
}

function prazoLabel(a: AcessoCliente): string {
  if (a.expirado) return "Vencido"
  if (a.validade_tipo === "data" && a.validade_ate) return `Expira ${fmtData(a.validade_ate)}`
  if (a.validade_tipo === "entrega") return "Até a entrega"
  return "Sem prazo"
}

const TIPOS: readonly [ValidadeTipo, string][] = [
  ["sem_prazo", "Sem prazo"],
  ["data", "Até data"],
  ["entrega", "Até a entrega"],
]

/** Seletor do prazo (tipo segmentado + data quando 'data'). Reusado no autorizar e na renovação. */
function PrazoFields({
  tipo,
  setTipo,
  ate,
  setAte,
}: {
  tipo: ValidadeTipo
  setTipo: (t: ValidadeTipo) => void
  ate: string | null
  setAte: (d: string | null) => void
}) {
  return (
    <div className="space-y-2">
      <div className="inline-flex flex-wrap gap-0.5 rounded-lg border border-border p-0.5 text-xs">
        {TIPOS.map(([v, l]) => (
          <button
            key={v}
            type="button"
            onClick={() => setTipo(v)}
            className={cn(
              "rounded-md px-2.5 py-1 transition-colors",
              tipo === v ? "bg-primary text-primary-foreground" : "text-muted-foreground",
            )}
          >
            {l}
          </button>
        ))}
      </div>
      {tipo === "data" && (
        <Input
          type="date"
          value={ate ?? ""}
          min={hojeISO()}
          onChange={(e) => setAte(e.target.value || null)}
        />
      )}
      {tipo === "entrega" && (
        <p className="text-xs text-muted-foreground">
          O acesso vence quando você marcar a obra como entregue.
        </p>
      )}
    </div>
  )
}

/** Acesso do cliente ao portal: o arquiteto autoriza o e-mail (+ prazo); o cliente se cadastra (senha
 * própria) e entra. No vencimento, o acesso é bloqueado (renovável aqui). */
export function AcessoClienteDialog({
  alvo,
  open,
  onOpenChange,
}: {
  alvo: AcessoAlvo
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const acessos = useAcessos(alvo, open)
  const lista = acessos.data ?? []
  const descricao =
    alvo.tipo === "projeto"
      ? "Autorize o e-mail do cliente e defina o prazo. Ele cria a senha no portal e acompanha o projeto e a obra."
      : "Autorize o e-mail do cliente e defina o prazo. Ele cria a senha no portal e acompanha a obra."

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Acesso do cliente</DialogTitle>
          <DialogDescription>{descricao}</DialogDescription>
        </DialogHeader>

        <div className="max-h-[70vh] space-y-6 overflow-y-auto">
          <AutorizarEmail alvo={alvo} />

          <section className="space-y-2">
            <Label>Acessos autorizados</Label>
            {acessos.isLoading ? (
              <CenteredSpinner />
            ) : lista.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nenhum cliente autorizado ainda.</p>
            ) : (
              <ul className="space-y-2">
                {lista.map((a) => (
                  <AcessoRow key={a.id} alvo={alvo} acesso={a} />
                ))}
              </ul>
            )}
          </section>

          <section className="space-y-2">
            <Label>Link do portal</Label>
            <div className="flex items-center justify-between gap-2 rounded-xl border border-border bg-card p-3">
              <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
                {portalCadastroUrl()}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => copiar(portalCadastroUrl(), "Link copiado")}
              >
                <Copy className="size-4" />
                Copiar
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Mande esse link pro cliente (ex.: WhatsApp). Ele se cadastra com o e-mail autorizado.
            </p>
          </section>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function AutorizarEmail({ alvo }: { alvo: AcessoAlvo }) {
  const [email, setEmail] = useState("")
  const [tipo, setTipo] = useState<ValidadeTipo>("sem_prazo")
  const [ate, setAte] = useState<string | null>(null)
  const autorizar = useAutorizarAcesso(alvo)
  const valido = /\S+@\S+\.\S+/.test(email)
  const prazoOk = tipo !== "data" || Boolean(ate)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || !prazoOk || autorizar.isPending) return
    try {
      await autorizar.mutateAsync({
        email,
        validade_tipo: tipo,
        validade_ate: tipo === "data" ? ate : null,
      })
      setEmail("")
      setTipo("sem_prazo")
      setAte(null)
      toast.success("E-mail autorizado — envie o link do portal pro cliente")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível autorizar.")
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="acesso-email">Autorizar e-mail</Label>
        <Input
          id="acesso-email"
          type="email"
          inputMode="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="cliente@email.com"
        />
      </div>
      <div className="space-y-1.5">
        <Label>Prazo de acesso</Label>
        <PrazoFields tipo={tipo} setTipo={setTipo} ate={ate} setAte={setAte} />
      </div>
      <Button type="submit" disabled={!valido || !prazoOk || autorizar.isPending}>
        {autorizar.isPending ? <Loader2 className="animate-spin" /> : <Mail />}
        Liberar acesso
      </Button>
    </form>
  )
}

function AcessoRow({ alvo, acesso }: { alvo: AcessoAlvo; acesso: AcessoCliente }) {
  const revogar = useRevogarAcesso(alvo)
  const definir = useDefinirPrazo(alvo)
  const [editando, setEditando] = useState(false)
  const [tipo, setTipo] = useState<ValidadeTipo>(acesso.validade_tipo)
  const [ate, setAte] = useState<string | null>(acesso.validade_ate)
  const prazoOk = tipo !== "data" || Boolean(ate)

  // a linha não desmonta (key estável) → ao abrir/cancelar, re-sincroniza do prop (não persiste edição
  // abandonada). Espelha o EtapaEditor (cujo state desmonta junto).
  function toggleEditor() {
    if (!editando) {
      setTipo(acesso.validade_tipo)
      setAte(acesso.validade_ate)
    }
    setEditando((v) => !v)
  }

  async function onRevogar() {
    try {
      await revogar.mutateAsync(acesso.id)
      toast.success("Acesso revogado")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível revogar.")
    }
  }

  async function salvarPrazo() {
    if (!prazoOk || definir.isPending) return
    try {
      await definir.mutateAsync({
        acessoId: acesso.id,
        validade_tipo: tipo,
        validade_ate: tipo === "data" ? ate : null,
      })
      setEditando(false)
      toast.success("Prazo atualizado")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar o prazo.")
    }
  }

  return (
    <li className="rounded-xl border border-border bg-card p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <Link2 className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="truncate text-sm font-medium">{acesso.email}</span>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[10px] uppercase tracking-wide">
            <span className={acesso.cadastrado ? "text-primary" : "text-muted-foreground"}>
              {acesso.cadastrado ? "Entrou" : "Aguardando cadastro"}
            </span>
            <span className={acesso.expirado ? "text-destructive" : "text-muted-foreground"}>
              · {prazoLabel(acesso)}
            </span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button variant="ghost" size="icon" aria-label="Definir prazo" onClick={toggleEditor}>
            <Clock className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            aria-label="Revogar acesso"
            disabled={revogar.isPending}
            onClick={onRevogar}
          >
            <Trash2 className="size-4 text-destructive" />
          </Button>
        </div>
      </div>

      {editando && (
        <div className="mt-3 space-y-2 border-t border-border pt-3">
          <PrazoFields tipo={tipo} setTipo={setTipo} ate={ate} setAte={setAte} />
          <div className="flex gap-2">
            <Button size="sm" onClick={salvarPrazo} disabled={!prazoOk || definir.isPending}>
              {definir.isPending && <Loader2 className="animate-spin" />}
              Salvar prazo
            </Button>
            <Button size="sm" variant="ghost" onClick={toggleEditor}>
              Cancelar
            </Button>
          </div>
        </div>
      )}
    </li>
  )
}
