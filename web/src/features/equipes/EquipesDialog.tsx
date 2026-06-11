import { Check, Loader2, Plus, Trash2 } from "lucide-react"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import {
  PALETA_EQUIPES,
  useAtualizarEquipe,
  useCriarEquipe,
  useEquipes,
  useExcluirEquipe,
  type Equipe,
} from "@/features/equipes/equipesApi"

/** Seletor de cor da paleta (poka-yoke: cores fixas e legíveis no Gantt). */
function PaletaCores({
  valor,
  onSelect,
}: {
  valor: string
  onSelect: (cor: string) => void
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {PALETA_EQUIPES.map((cor) => {
        const sel = cor.toUpperCase() === valor.toUpperCase()
        return (
          <button
            key={cor}
            type="button"
            aria-label={`Cor ${cor}`}
            onClick={() => onSelect(cor)}
            className={cn(
              "flex size-6 items-center justify-center rounded-full transition-transform hover:scale-110",
              sel && "ring-2 ring-foreground ring-offset-2 ring-offset-card",
            )}
            style={{ background: cor }}
          >
            {sel && <Check className="size-3.5 text-black/70" />}
          </button>
        )
      })}
    </div>
  )
}

/**
 * Gestão da biblioteca de EQUIPES do escritório (nível-tenant, reutilizável entre obras): criar,
 * renomear, trocar a cor (Gantt), contato e excluir (desliga das tarefas, sem apagá-las).
 * Poka-yoke: cores fixas; excluir pede confirmação inline.
 */
export function EquipesDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const equipes = useEquipes(open)
  const criar = useCriarEquipe()
  const atualizar = useAtualizarEquipe()
  const excluir = useExcluirEquipe()

  const [nome, setNome] = useState("")
  const [cor, setCor] = useState<string>(PALETA_EQUIPES[0])
  const [confirmando, setConfirmando] = useState<string | null>(null)

  async function adicionar(e: FormEvent) {
    e.preventDefault()
    const limpo = nome.trim()
    if (!limpo) return
    try {
      await criar.mutateAsync({ nome: limpo, cor })
      // limpa só no SUCESSO: no 409 (nome duplicado) ou erro de rede o usuário não perde o que digitou.
      setNome("")
      setCor(PALETA_EQUIPES[0])
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível adicionar.")
    }
  }

  async function renomear(eq: Equipe, novo: string) {
    const limpo = novo.trim()
    if (!limpo || limpo === eq.nome) return
    try {
      await atualizar.mutateAsync({ id: eq.id, patch: { nome: limpo } })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível renomear.")
    }
  }

  async function recolorir(eq: Equipe, novaCor: string) {
    if (novaCor.toUpperCase() === eq.cor.toUpperCase()) return
    try {
      await atualizar.mutateAsync({ id: eq.id, patch: { cor: novaCor } })
    } catch {
      toast.error("Não foi possível trocar a cor.")
    }
  }

  async function setContato(eq: Equipe, raw: string) {
    const v = raw.trim() || null
    if (v === (eq.contato ?? null)) return
    try {
      await atualizar.mutateAsync({ id: eq.id, patch: { contato: v } })
    } catch {
      toast.error("Não foi possível salvar o contato.")
    }
  }

  async function remover(eq: Equipe) {
    setConfirmando(null)
    try {
      await excluir.mutateAsync(eq.id)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível excluir.")
    }
  }

  const lista = equipes.data ?? []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Equipes do escritório</DialogTitle>
          <DialogDescription>
            Cadastre suas turmas (Elétrica, Hidráulica, Gesso…) com uma cor para ler o Gantt. A
            biblioteca é reutilizável em todas as obras; excluir só desliga a equipe das tarefas.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {equipes.isLoading ? (
            <div className="flex justify-center py-6">
              <Loader2 className="size-5 animate-spin text-muted-foreground" />
            </div>
          ) : lista.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
              Nenhuma equipe ainda. Cadastre a primeira abaixo.
            </p>
          ) : (
            <ul className="max-h-[50vh] space-y-2 overflow-y-auto">
              {lista.map((eq) => (
                // key inclui nome/cor/contato: força remount dos inputs uncontrolled quando o
                // servidor canoniza o valor (evita input "stale").
                <li
                  key={`${eq.id}:${eq.nome}:${eq.cor}:${eq.contato ?? ""}`}
                  className="space-y-2 rounded-lg border border-border p-2.5"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="size-4 shrink-0 rounded-full"
                      style={{ background: eq.cor }}
                      aria-hidden
                    />
                    <Input
                      defaultValue={eq.nome}
                      maxLength={120}
                      aria-label="Nome da equipe"
                      onBlur={(e) => void renomear(eq, e.target.value)}
                      className="h-9 min-w-0 flex-1"
                    />
                    {confirmando === eq.id ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="destructive"
                        disabled={excluir.isPending}
                        onClick={() => void remover(eq)}
                      >
                        {excluir.isPending ? <Loader2 className="animate-spin" /> : "Excluir"}
                      </Button>
                    ) : (
                      <button
                        type="button"
                        aria-label="Excluir equipe"
                        onClick={() => setConfirmando(eq.id)}
                        className="shrink-0 rounded-md p-1.5 text-muted-foreground transition-colors hover:text-destructive"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    )}
                  </div>
                  <Input
                    defaultValue={eq.contato ?? ""}
                    maxLength={200}
                    aria-label="Contato da equipe"
                    placeholder="Contato (telefone, responsável…)"
                    onBlur={(e) => void setContato(eq, e.target.value)}
                    className="h-9"
                  />
                  <PaletaCores valor={eq.cor} onSelect={(c) => void recolorir(eq, c)} />
                </li>
              ))}
            </ul>
          )}

          <form onSubmit={adicionar} className="space-y-2 border-t border-border pt-3">
            <div className="flex items-center gap-2">
              <span className="size-4 shrink-0 rounded-full" style={{ background: cor }} aria-hidden />
              <Input
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                maxLength={120}
                placeholder="Nova equipe…"
                className="min-w-0 flex-1"
              />
              <Button type="submit" disabled={!nome.trim() || criar.isPending} className="shrink-0">
                {criar.isPending ? <Loader2 className="animate-spin" /> : <Plus />}
                Adicionar
              </Button>
            </div>
            <PaletaCores valor={cor} onSelect={setCor} />
          </form>
        </div>
      </DialogContent>
    </Dialog>
  )
}
