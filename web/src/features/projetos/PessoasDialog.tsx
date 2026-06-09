import { Copy, KeyRound, Loader2, Mail, RotateCw, Trash2, X } from "lucide-react"
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
  useCodigo,
  useConvidar,
  useGerarCodigo,
  useMembros,
  useRemoverMembro,
  useRevogarCodigo,
  type ProjetoMembro,
} from "@/features/projetos/projetosApi"

const horaFmt = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })

async function copiar(texto: string, msg: string) {
  try {
    await navigator.clipboard.writeText(texto)
    toast.success(msg)
  } catch {
    toast.error("Não consegui copiar — copie manualmente.")
  }
}

export function PessoasDialog({
  projetoId,
  open,
  onOpenChange,
}: {
  projetoId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const membros = useMembros(projetoId, open)
  const lista = membros.data ?? []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Pessoas</DialogTitle>
          <DialogDescription>Convide o cliente por email ou compartilhe um código.</DialogDescription>
        </DialogHeader>

        <div className="max-h-[70vh] space-y-6 overflow-y-auto">
          <section className="space-y-2">
            <Label>Membros</Label>
            {membros.isLoading ? (
              <CenteredSpinner />
            ) : lista.length === 0 ? (
              <p className="text-sm text-muted-foreground">Só você por enquanto.</p>
            ) : (
              <ul className="space-y-2">
                {lista.map((m) => (
                  <MembroRow key={m.id} projetoId={projetoId} membro={m} />
                ))}
              </ul>
            )}
          </section>

          <ConviteEmail projetoId={projetoId} />
          <CodigoSection projetoId={projetoId} open={open} />
        </div>
      </DialogContent>
    </Dialog>
  )
}

function MembroRow({ projetoId, membro }: { projetoId: string; membro: ProjetoMembro }) {
  const remover = useRemoverMembro(projetoId)
  const ehArquiteto = membro.papel === "arquiteto"

  async function onRemover() {
    try {
      await remover.mutateAsync(membro.id)
      toast.success("Membro removido")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível remover.")
    }
  }

  return (
    <li className="flex items-center justify-between gap-2 rounded-xl border border-border bg-card p-3">
      <div className="min-w-0">
        <div className="break-words text-sm font-medium">{membro.nome || membro.email || "—"}</div>
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="uppercase tracking-wide">{ehArquiteto ? "Arquiteto" : "Cliente"}</span>
          {membro.estado !== "ativo" && (
            <span className="rounded-full bg-accent px-1.5 py-0.5 text-[10px] uppercase text-primary">
              {membro.estado}
            </span>
          )}
        </div>
      </div>
      {!ehArquiteto && (
        <Button
          variant="ghost"
          size="icon"
          aria-label="Remover membro"
          disabled={remover.isPending}
          onClick={onRemover}
        >
          <Trash2 className="size-4 text-destructive" />
        </Button>
      )}
    </li>
  )
}

function ConviteEmail({ projetoId }: { projetoId: string }) {
  const [email, setEmail] = useState("")
  const [link, setLink] = useState<string | null>(null)
  const convidar = useConvidar(projetoId)
  const valido = /\S+@\S+\.\S+/.test(email)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || convidar.isPending) return
    try {
      const res = await convidar.mutateAsync(email)
      setEmail("")
      if (res.action_link) {
        setLink(res.action_link)
        toast.success("Convite criado — envie o link de acesso ao cliente")
      } else {
        toast.success("Convite enviado — aparecerá nos convites pendentes do cliente")
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível convidar.")
    }
  }

  return (
    <section className="space-y-2">
      <Label htmlFor="convite-email">Convidar por email</Label>
      <form onSubmit={onSubmit} className="flex gap-2">
        <Input
          id="convite-email"
          type="email"
          inputMode="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="cliente@email.com"
        />
        <Button type="submit" disabled={!valido || convidar.isPending}>
          {convidar.isPending ? <Loader2 className="animate-spin" /> : <Mail />}
          Convidar
        </Button>
      </form>
      {link && (
        <div className="rounded-xl border border-primary/40 bg-primary/5 p-3">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-xs font-medium text-primary">Link de acesso (usuário novo)</span>
            <button type="button" onClick={() => setLink(null)} aria-label="Fechar">
              <X className="size-3.5 text-muted-foreground" />
            </button>
          </div>
          <p className="mb-2 break-all text-xs text-muted-foreground">{link}</p>
          <Button size="sm" variant="outline" className="w-full" onClick={() => copiar(link, "Link copiado")}>
            <Copy />
            Copiar link
          </Button>
        </div>
      )}
    </section>
  )
}

function CodigoSection({ projetoId, open }: { projetoId: string; open: boolean }) {
  const codigo = useCodigo(projetoId, open)
  const gerar = useGerarCodigo(projetoId)
  const revogar = useRevogarCodigo(projetoId)
  const ativo = codigo.data ?? null

  async function onGerar() {
    try {
      const novo = await gerar.mutateAsync()
      toast.success("Código gerado")
      void copiar(novo.codigo, "Código copiado")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível gerar o código.")
    }
  }

  async function onRevogar() {
    try {
      await revogar.mutateAsync()
      toast.success("Código revogado")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível revogar.")
    }
  }

  return (
    <section className="space-y-2">
      <Label>Código do projeto</Label>
      {codigo.isLoading ? (
        <div className="h-11 animate-pulse rounded-xl bg-accent/40" />
      ) : ativo ? (
        <div className="space-y-2 rounded-xl border border-border bg-card p-3">
          <div className="flex items-center justify-between gap-2">
            <span className={cn("font-display text-2xl tracking-[0.25em]")}>{ativo.codigo}</span>
            <Button variant="ghost" size="icon" aria-label="Copiar código" onClick={() => copiar(ativo.codigo, "Código copiado")}>
              <Copy className="size-4" />
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Válido até {horaFmt.format(new Date(ativo.expires_at))} · uso único por pessoa
          </p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" className="flex-1" disabled={gerar.isPending} onClick={onGerar}>
              <RotateCw />
              Gerar novo
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="flex-1 text-destructive hover:bg-destructive/10 hover:text-destructive"
              disabled={revogar.isPending}
              onClick={onRevogar}
            >
              Revogar
            </Button>
          </div>
        </div>
      ) : (
        <Button variant="outline" className="w-full" disabled={gerar.isPending} onClick={onGerar}>
          {gerar.isPending ? <Loader2 className="animate-spin" /> : <KeyRound />}
          Gerar código
        </Button>
      )}
    </section>
  )
}
