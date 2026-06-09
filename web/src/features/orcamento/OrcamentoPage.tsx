import {
  Calculator,
  ChevronLeft,
  FileUp,
  Loader2,
  Lock,
  Pencil,
  Plus,
  Send,
  SlidersHorizontal,
  Trash2,
} from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { toast } from "sonner"

import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Button } from "@/components/ui/button"
import { ConfirmDialog } from "@/components/ui/confirm-dialog"
import { cn } from "@/lib/utils"
import { ApiError } from "@/lib/api"
import { formatBRL } from "@/features/comercial/format"
import { useProjeto } from "@/features/projetos/projetosApi"
import { ItemDialog } from "@/features/orcamento/ItemDialog"
import { ParamsDialog } from "@/features/orcamento/ParamsDialog"
import {
  useAtualizarParams,
  useCriarVersao,
  useExcluirItem,
  useImportarOrcamento,
  useVersao,
  useVersoes,
  type OrcItem,
} from "@/features/orcamento/orcamentosApi"

const dataFmt = (iso: string | null) => {
  if (!iso) return "—"
  const [y, m, d] = iso.split("-")
  return `${d}/${m}/${y.slice(2)}`
}
const pctFmt = (n: number) => `${String(n).replace(".", ",")}%`

export function OrcamentoPage() {
  const { projetoId = "" } = useParams()
  const projeto = useProjeto(projetoId)
  const ehArquiteto = projeto.data?.meu_papel === "arquiteto"
  const versoes = useVersoes(projetoId)
  const [selId, setSelId] = useState<string | null>(null)

  // seleciona a versão editável por padrão (ou a última); mantém a escolha se ainda existir
  useEffect(() => {
    const lista = versoes.data
    if (!lista || lista.length === 0) return
    const editavel = lista.find((v) => !v.congelado)
    const alvo = editavel?.id ?? lista[lista.length - 1].id
    setSelId((prev) => (prev && lista.some((v) => v.id === prev) ? prev : alvo))
  }, [versoes.data])

  const versao = useVersao(projetoId, selId)
  const criar = useCriarVersao(projetoId)
  const setParams = useAtualizarParams(projetoId, selId ?? "")
  const importar = useImportarOrcamento(projetoId, selId ?? "")
  const excluirItem = useExcluirItem(projetoId, selId ?? "")

  const [confirmNova, setConfirmNova] = useState(false)
  const [paramsOpen, setParamsOpen] = useState(false)
  const [itemDialog, setItemDialog] = useState<{ item?: OrcItem; etapa?: string } | null>(null)
  const [excluindo, setExcluindo] = useState<OrcItem | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const v = versao.data
  const editavel = v != null && !v.congelado
  const temVersoes = (versoes.data?.length ?? 0) > 0
  const etapasNomes = v ? v.etapas.map((e) => e.etapa) : []

  async function novaVersao(primeira: boolean) {
    try {
      const nova = await criar.mutateAsync()
      setSelId(nova.id)
      toast.success(primeira ? "Orçamento criado" : `Nova versão · R${nova.numero}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível criar a versão.")
    }
  }

  async function onToggleEnviado() {
    if (!v || v.congelado) return
    try {
      await setParams.mutateAsync({ enviado: !v.enviado })
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível atualizar.")
    }
  }

  async function onArquivo(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file) return
    try {
      await importar.mutateAsync(file)
      toast.success("Planilha importada")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível importar.")
    }
  }

  async function onExcluirItem() {
    if (!excluindo) return
    try {
      await excluirItem.mutateAsync(excluindo.id)
      setExcluindo(null)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível excluir.")
    }
  }

  return (
    <div className="animate-fade-up">
      <Link
        to={`/projetos/${projetoId}`}
        className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ChevronLeft className="size-4" />
        {projeto.data?.nome ?? "Projeto"}
      </Link>

      <div className="mb-4 flex items-end justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Proposta comercial</div>
          <h1 className="font-word text-4xl leading-none">ORÇAMENTO</h1>
        </div>
        {ehArquiteto && temVersoes && (
          <div className="flex gap-2">
            <input ref={fileRef} type="file" accept=".xlsx" className="hidden" onChange={onArquivo} />
            <Button
              variant="outline"
              size="icon"
              title="Importar planilha"
              aria-label="Importar planilha"
              disabled={!editavel || importar.isPending}
              onClick={() => fileRef.current?.click()}
            >
              {importar.isPending ? <Loader2 className="animate-spin" /> : <FileUp />}
            </Button>
            <Button onClick={() => setConfirmNova(true)} disabled={criar.isPending}>
              <Plus />
              Nova versão
            </Button>
          </div>
        )}
      </div>

      {(projeto.isLoading || versoes.isLoading) && <CenteredSpinner />}

      {projeto.isSuccess && !ehArquiteto && (
        <EmptyState
          icon={Lock}
          title="Acesso restrito"
          description="Apenas o arquiteto acessa o orçamento do projeto."
        />
      )}

      {versoes.isError && (
        <ErrorState message="Não foi possível carregar o orçamento." onRetry={() => void versoes.refetch()} />
      )}

      {ehArquiteto && versoes.isSuccess && !temVersoes && (
        <EmptyState
          icon={Calculator}
          title="Nenhum orçamento ainda"
          description="Crie a primeira versão e monte os serviços (à mão ou importando uma planilha)."
          action={
            <Button onClick={() => void novaVersao(true)} disabled={criar.isPending}>
              {criar.isPending ? <Loader2 className="animate-spin" /> : <Plus />}
              Criar orçamento
            </Button>
          }
        />
      )}

      {ehArquiteto && temVersoes && (
        <>
          {/* seletor de versões (R0/R1…) — comparação de preço ao lado */}
          <div className="-mx-5 mb-4 flex gap-1.5 overflow-x-auto px-5 pb-1">
            {versoes.data!.map((rv) => {
              const ativo = rv.id === selId
              return (
                <button
                  key={rv.id}
                  type="button"
                  onClick={() => setSelId(rv.id)}
                  className={cn(
                    "inline-flex shrink-0 items-center gap-1.5 rounded-xl border px-3 py-1.5 text-left text-xs transition-colors",
                    ativo ? "border-primary bg-primary/10" : "border-border hover:border-primary/40",
                  )}
                >
                  <span className="font-display font-semibold">R{rv.numero}</span>
                  {rv.congelado && <Lock className="size-3 text-muted-foreground" />}
                  {rv.enviado && <Send className="size-3 text-primary" />}
                  <span className="text-muted-foreground">{formatBRL(rv.preco_final)}</span>
                </button>
              )
            })}
          </div>

          {versao.isLoading && <CenteredSpinner />}

          {v && (
            <>
              {/* resumo (KPIs do preço) */}
              <div className="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <Kpi label="Custo direto" valor={formatBRL(v.totais.custo_direto)} />
                <Kpi label={`BDI ${pctFmt(v.bdi)}`} valor={formatBRL(v.totais.bdi_valor)} />
                <Kpi label={`Imposto ${pctFmt(v.imposto)}`} valor={formatBRL(v.totais.imposto_valor)} />
                <Kpi label="Preço final" valor={formatBRL(v.totais.preco_final)} destaque />
              </div>

              {/* parâmetros + status */}
              <div className="mb-4 rounded-2xl border border-border bg-card p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-sm">
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
                      <span>Data: <span className="text-foreground">{dataFmt(v.data)}</span></span>
                      <span>Validade: <span className="text-foreground">{dataFmt(v.validade)}</span></span>
                      <span>
                        Majoração:{" "}
                        <span className="text-foreground">
                          M.O {pctFmt(v.maj_mo)} · Mat {pctFmt(v.maj_material)} · Eq {pctFmt(v.maj_equipamento)}
                        </span>
                      </span>
                    </div>
                  </div>
                  {editavel && (
                    <Button variant="outline" size="sm" onClick={() => setParamsOpen(true)}>
                      <SlidersHorizontal />
                      Parâmetros
                    </Button>
                  )}
                </div>
                <div className="mt-3 flex items-center justify-between gap-3 border-t border-border pt-3">
                  <span className="text-sm text-muted-foreground">
                    {v.congelado ? "Versão congelada (somente leitura)" : "Versão em edição"}
                  </span>
                  {editavel ? (
                    <Button
                      variant={v.enviado ? "default" : "outline"}
                      size="sm"
                      disabled={setParams.isPending}
                      onClick={onToggleEnviado}
                    >
                      <Send />
                      {v.enviado ? "Enviado ao cliente" : "Marcar como enviado"}
                    </Button>
                  ) : v.enviado ? (
                    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-primary">
                      <Send className="size-3.5" />
                      Enviado ao cliente
                    </span>
                  ) : null}
                </div>
              </div>

              {/* itens por etapa */}
              {editavel && (
                <div className="mb-3 flex justify-end">
                  <Button variant="outline" size="sm" onClick={() => setItemDialog({})}>
                    <Plus />
                    Etapa / serviço
                  </Button>
                </div>
              )}

              {v.etapas.length === 0 ? (
                <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
                  Nenhum serviço ainda.{editavel ? " Adicione à mão ou importe uma planilha." : ""}
                </p>
              ) : (
                <div className="space-y-4">
                  {v.etapas.map((g) => (
                    <div key={g.etapa} className="rounded-2xl border border-border bg-card">
                      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2">
                        <span className="break-words text-sm font-semibold uppercase tracking-wide">
                          {g.etapa}
                        </span>
                        <div className="flex shrink-0 items-center gap-2">
                          <span className="font-display text-sm tabular-nums text-muted-foreground">
                            {formatBRL(g.custo_direto)}
                          </span>
                          {editavel && (
                            <button
                              type="button"
                              aria-label="Adicionar serviço nesta etapa"
                              title="Adicionar serviço"
                              className="rounded-md p-1 text-muted-foreground hover:text-foreground"
                              onClick={() => setItemDialog({ etapa: g.etapa })}
                            >
                              <Plus className="size-4" />
                            </button>
                          )}
                        </div>
                      </div>
                      <ul className="divide-y divide-border">
                        {g.itens.map((it) => (
                          <ItemRow
                            key={it.id}
                            item={it}
                            editavel={editavel}
                            onEdit={() => setItemDialog({ item: it })}
                            onDelete={() => setExcluindo(it)}
                          />
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              )}

              {v.observacoes && (
                <div className="mt-4 rounded-2xl border border-border bg-card p-4">
                  <div className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">Observações</div>
                  <p className="whitespace-pre-wrap break-words text-sm">{v.observacoes}</p>
                </div>
              )}
            </>
          )}
        </>
      )}

      <ConfirmDialog
        open={confirmNova}
        onOpenChange={setConfirmNova}
        title="Nova versão do orçamento"
        description="A versão atual será congelada (só-leitura) e uma cópia editável será criada para a nova revisão."
        confirmLabel="Criar nova versão"
        pending={criar.isPending}
        onConfirm={async () => {
          setConfirmNova(false)
          await novaVersao(false)
        }}
      />
      {v && (
        <>
          <ParamsDialog open={paramsOpen} onOpenChange={setParamsOpen} projetoId={projetoId} versao={v} />
          <ItemDialog
            open={itemDialog !== null}
            onOpenChange={(o) => {
              if (!o) setItemDialog(null)
            }}
            projetoId={projetoId}
            versaoId={v.id}
            item={itemDialog?.item}
            etapaPadrao={itemDialog?.etapa}
            etapasExistentes={etapasNomes}
          />
        </>
      )}
      <ConfirmDialog
        open={excluindo !== null}
        onOpenChange={(o) => {
          if (!o) setExcluindo(null)
        }}
        title="Excluir serviço"
        description={excluindo ? `Remover "${excluindo.descricao}" do orçamento?` : ""}
        pending={excluirItem.isPending}
        onConfirm={onExcluirItem}
      />
    </div>
  )
}

function Kpi({ label, valor, destaque }: { label: string; valor: string; destaque?: boolean }) {
  return (
    <div
      className={cn(
        "flex flex-col rounded-2xl border bg-card p-3",
        destaque ? "border-primary/50" : "border-border",
      )}
    >
      <span className="text-[10px] font-medium uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </span>
      <span
        className={cn("mt-1 font-display text-xl leading-none tabular-nums", destaque && "text-primary")}
      >
        {valor}
      </span>
    </div>
  )
}

function ItemRow({
  item,
  editavel,
  onEdit,
  onDelete,
}: {
  item: OrcItem
  editavel: boolean
  onEdit: () => void
  onDelete: () => void
}) {
  const subtotal = item.valor_mo + item.valor_material + item.valor_equipamento
  return (
    <li className="flex items-start gap-2 px-4 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="break-words text-sm font-medium">{item.descricao}</p>
        <div className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
          {(item.quantidade != null || item.unidade) && (
            <span>
              {item.quantidade != null ? String(item.quantidade).replace(".", ",") : ""}
              {item.unidade ? ` ${item.unidade}` : ""}
            </span>
          )}
          <span>M.O {formatBRL(item.valor_mo)}</span>
          <span>Mat {formatBRL(item.valor_material)}</span>
          <span>Eq {formatBRL(item.valor_equipamento)}</span>
        </div>
      </div>
      <span className="shrink-0 font-display text-sm tabular-nums">{formatBRL(subtotal)}</span>
      {editavel && (
        <div className="flex shrink-0 gap-0.5">
          <button
            type="button"
            aria-label="Editar"
            className="rounded-md p-1 text-muted-foreground hover:text-foreground"
            onClick={onEdit}
          >
            <Pencil className="size-3.5" />
          </button>
          <button
            type="button"
            aria-label="Excluir"
            className="rounded-md p-1 text-muted-foreground hover:text-destructive"
            onClick={onDelete}
          >
            <Trash2 className="size-3.5" />
          </button>
        </div>
      )}
    </li>
  )
}
