import { Loader2, Plus, Trash2 } from "lucide-react"
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
import {
  useAtualizarFuncao,
  useCriarFuncao,
  useExcluirFuncao,
  useFuncoes,
  type Funcao,
} from "@/features/funcoes/funcoesApi"

/**
 * Gestão da biblioteca de FUNÇÕES/cargos do escritório (nível-tenant, reutilizável entre obras):
 * Pedreiro, Servente, Mestre de obras… Usadas no efetivo do diário (função × quantidade).
 * Poka-yoke: excluir pede confirmação inline; excluir não mexe no histórico (o nome no efetivo é
 * snapshot). É arquiteto-only (RLS self).
 */
export function FuncoesDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const funcoes = useFuncoes(open)
  const criar = useCriarFuncao()
  const atualizar = useAtualizarFuncao()
  const excluir = useExcluirFuncao()

  const [nome, setNome] = useState("")
  const [confirmando, setConfirmando] = useState<string | null>(null)

  async function adicionar(e: FormEvent) {
    e.preventDefault()
    const limpo = nome.trim()
    if (!limpo) return
    try {
      await criar.mutateAsync({ nome: limpo })
      setNome("") // limpa só no SUCESSO (no 409/erro o usuário não perde o que digitou)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível adicionar.")
    }
  }

  async function renomear(f: Funcao, novo: string) {
    const limpo = novo.trim()
    if (!limpo || limpo === f.nome) return
    try {
      await atualizar.mutateAsync({ id: f.id, patch: { nome: limpo } })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível renomear.")
    }
  }

  async function remover(f: Funcao) {
    setConfirmando(null)
    try {
      await excluir.mutateAsync(f.id)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível excluir.")
    }
  }

  const lista = funcoes.data ?? []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Funções / cargos</DialogTitle>
          <DialogDescription>
            Cadastre os cargos usados no efetivo do diário (Pedreiro, Servente, Mestre de obras…). A
            biblioteca é reutilizável em todas as obras.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {funcoes.isLoading ? (
            <div className="flex justify-center py-6">
              <Loader2 className="size-5 animate-spin text-muted-foreground" />
            </div>
          ) : lista.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
              Nenhuma função ainda. Cadastre a primeira abaixo.
            </p>
          ) : (
            <ul className="max-h-[50vh] space-y-2 overflow-y-auto">
              {lista.map((f) => (
                <li
                  key={`${f.id}:${f.nome}`}
                  className="flex items-center gap-2 rounded-lg border border-border p-2.5"
                >
                  <Input
                    defaultValue={f.nome}
                    maxLength={120}
                    aria-label="Nome da função"
                    onBlur={(e) => void renomear(f, e.target.value)}
                    className="h-9 min-w-0 flex-1"
                  />
                  {confirmando === f.id ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="destructive"
                      disabled={excluir.isPending}
                      onClick={() => void remover(f)}
                    >
                      {excluir.isPending ? <Loader2 className="animate-spin" /> : "Excluir"}
                    </Button>
                  ) : (
                    <button
                      type="button"
                      aria-label="Excluir função"
                      onClick={() => setConfirmando(f.id)}
                      className="shrink-0 rounded-md p-1.5 text-muted-foreground transition-colors hover:text-destructive"
                    >
                      <Trash2 className="size-4" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}

          <form onSubmit={adicionar} className="flex items-center gap-2 border-t border-border pt-3">
            <Input
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              maxLength={120}
              placeholder="Nova função…"
              className="min-w-0 flex-1"
            />
            <Button type="submit" disabled={!nome.trim() || criar.isPending} className="shrink-0">
              {criar.isPending ? <Loader2 className="animate-spin" /> : <Plus />}
              Adicionar
            </Button>
          </form>
        </div>
      </DialogContent>
    </Dialog>
  )
}
