import { BookMarked, Pencil, Plus, Search, Trash2 } from "lucide-react"
import { useMemo, useState } from "react"
import { toast } from "sonner"

import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/lib/api"
import { formatBRL } from "@/features/comercial/format"
import { ServicoDialog } from "@/features/catalogo/ServicoDialog"
import {
  useCatalogo,
  useExcluirServico,
  type ServicoCatalogo,
} from "@/features/catalogo/catalogoApi"

export function CatalogoPage() {
  const catalogo = useCatalogo()
  const excluir = useExcluirServico()
  const [busca, setBusca] = useState("")
  const [dialog, setDialog] = useState<{ servico?: ServicoCatalogo } | null>(null)
  const [excluindo, setExcluindo] = useState<ServicoCatalogo | null>(null)

  const servicos = catalogo.data ?? []
  const etapasSugeridas = useMemo(
    () => [...new Set(servicos.map((s) => s.etapa_sugerida).filter((e): e is string => !!e))].sort(),
    [servicos],
  )
  const filtrados = useMemo(() => {
    const q = busca.trim().toLowerCase()
    if (!q) return servicos
    return servicos.filter(
      (s) =>
        s.descricao.toLowerCase().includes(q) ||
        (s.etapa_sugerida ?? "").toLowerCase().includes(q),
    )
  }, [servicos, busca])

  async function onExcluir() {
    if (!excluindo) return
    try {
      await excluir.mutateAsync(excluindo.id)
      setExcluindo(null)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível excluir.")
    }
  }

  return (
    <div className="animate-fade-up">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Livro de referências</div>
          <h1 className="font-word text-4xl leading-none">CATÁLOGO</h1>
        </div>
        <Button onClick={() => setDialog({})}>
          <Plus />
          Novo serviço
        </Button>
      </div>

      <p className="mb-4 text-sm text-muted-foreground">
        Serviços reutilizáveis com <strong>custo de referência por unidade</strong>. Use-os ao montar
        orçamentos para ganhar velocidade e coerência — o valor multiplica pela quantidade.
      </p>

      {catalogo.isLoading && <CenteredSpinner />}
      {catalogo.isError && (
        <ErrorState message="Não foi possível carregar o catálogo." onRetry={() => void catalogo.refetch()} />
      )}

      {catalogo.isSuccess && servicos.length === 0 && (
        <EmptyState
          icon={BookMarked}
          title="Catálogo vazio"
          description="Cadastre serviços aqui, ou salve no catálogo direto de uma linha de orçamento que você já montou."
          action={
            <Button onClick={() => setDialog({})}>
              <Plus />
              Novo serviço
            </Button>
          }
        />
      )}

      {catalogo.isSuccess && servicos.length > 0 && (
        <>
          <div className="relative mb-3">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar serviço…"
              className="pl-9"
            />
          </div>

          {filtrados.length === 0 ? (
            <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
              Nenhum serviço encontrado.
            </p>
          ) : (
            <ul className="space-y-2">
              {filtrados.map((s) => {
                const total = s.custo_mo + s.custo_material + s.custo_equipamento
                return (
                  <li
                    key={s.id}
                    className="flex items-start gap-2 rounded-2xl border border-border bg-card px-4 py-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="break-words text-sm font-medium">{s.descricao}</p>
                        {s.etapa_sugerida && (
                          <span className="rounded-md bg-accent px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                            {s.etapa_sugerida}
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                        <span>M.O {formatBRL(s.custo_mo)}</span>
                        <span>Mat {formatBRL(s.custo_material)}</span>
                        <span>Eq {formatBRL(s.custo_equipamento)}</span>
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="font-display text-sm tabular-nums">{formatBRL(total)}</div>
                      <div className="text-[10px] uppercase text-muted-foreground">
                        / {s.unidade || "un"}
                      </div>
                    </div>
                    <div className="flex shrink-0 gap-0.5">
                      <button
                        type="button"
                        aria-label="Editar"
                        className="rounded-md p-1 text-muted-foreground hover:text-foreground"
                        onClick={() => setDialog({ servico: s })}
                      >
                        <Pencil className="size-3.5" />
                      </button>
                      <button
                        type="button"
                        aria-label="Excluir"
                        className="rounded-md p-1 text-muted-foreground hover:text-destructive"
                        onClick={() => setExcluindo(s)}
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </>
      )}

      <ServicoDialog
        open={dialog !== null}
        onOpenChange={(o) => {
          if (!o) setDialog(null)
        }}
        servico={dialog?.servico}
        etapasSugeridas={etapasSugeridas}
      />
      <ConfirmDialog
        open={excluindo !== null}
        onOpenChange={(o) => {
          if (!o) setExcluindo(null)
        }}
        title="Excluir serviço"
        description={excluindo ? `Remover "${excluindo.descricao}" do catálogo?` : ""}
        pending={excluir.isPending}
        onConfirm={onExcluir}
      />
    </div>
  )
}
