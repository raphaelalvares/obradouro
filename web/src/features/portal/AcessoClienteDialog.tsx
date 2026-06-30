import { Copy, Link2, Loader2, Mail, Trash2 } from "lucide-react"
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
import {
  portalCadastroUrl,
  useAcessos,
  useAutorizarAcesso,
  useRevogarAcesso,
  type AcessoAlvo,
  type AcessoCliente,
} from "@/features/portal/portalApi"

async function copiar(texto: string, msg: string) {
  try {
    await navigator.clipboard.writeText(texto)
    toast.success(msg)
  } catch {
    toast.error("Não consegui copiar — copie manualmente.")
  }
}

/** Acesso do cliente ao portal: o arquiteto autoriza o e-mail; o cliente se cadastra (senha própria)
 * e entra. Diferente de "Pessoas" (convite por e-mail do Supabase): aqui o cliente se AUTOCADASTRA. */
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
      ? "Autorize o e-mail do cliente. Ele cria a própria senha no portal e acompanha o projeto e a obra."
      : "Autorize o e-mail do cliente. Ele cria a própria senha no portal e acompanha a obra."

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
  const autorizar = useAutorizarAcesso(alvo)
  const valido = /\S+@\S+\.\S+/.test(email)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || autorizar.isPending) return
    try {
      await autorizar.mutateAsync(email)
      setEmail("")
      toast.success("E-mail autorizado — envie o link do portal pro cliente")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível autorizar.")
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-2">
      <Label htmlFor="acesso-email">Autorizar e-mail</Label>
      <div className="flex gap-2">
        <Input
          id="acesso-email"
          type="email"
          inputMode="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="cliente@email.com"
        />
        <Button type="submit" disabled={!valido || autorizar.isPending}>
          {autorizar.isPending ? <Loader2 className="animate-spin" /> : <Mail />}
          Liberar
        </Button>
      </div>
    </form>
  )
}

function AcessoRow({ alvo, acesso }: { alvo: AcessoAlvo; acesso: AcessoCliente }) {
  const revogar = useRevogarAcesso(alvo)

  async function onRevogar() {
    try {
      await revogar.mutateAsync(acesso.id)
      toast.success("Acesso revogado")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível revogar.")
    }
  }

  return (
    <li className="flex items-center justify-between gap-2 rounded-xl border border-border bg-card p-3">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <Link2 className="size-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate text-sm font-medium">{acesso.email}</span>
        </div>
        <span
          className={
            acesso.cadastrado
              ? "text-[10px] uppercase tracking-wide text-primary"
              : "text-[10px] uppercase tracking-wide text-muted-foreground"
          }
        >
          {acesso.cadastrado ? "Entrou" : "Aguardando cadastro"}
        </span>
      </div>
      <Button
        variant="ghost"
        size="icon"
        aria-label="Revogar acesso"
        disabled={revogar.isPending}
        onClick={onRevogar}
      >
        <Trash2 className="size-4 text-destructive" />
      </Button>
    </li>
  )
}
