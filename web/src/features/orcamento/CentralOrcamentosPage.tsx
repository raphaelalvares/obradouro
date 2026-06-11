import { Calculator, ChevronRight, Send } from "lucide-react"
import { useMemo, useState } from "react"
import { Link, useNavigate } from "react-router-dom"

import { CenteredSpinner, EmptyState, ErrorState } from "@/components/feedback/states"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { formatBRL, formatData, hojeISO } from "@/features/comercial/format"
import { useCentralOrcamentos, type OrcamentoCentral } from "@/features/orcamento/orcamentosApi"

type Filtro = "todos" | "com" | "enviados" | "sem"

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "todos", label: "Todos" },
  { key: "com", label: "Com orçamento" },
  { key: "enviados", label: "Enviados" },
  { key: "sem", label: "Sem orçamento" },
]

export function CentralOrcamentosPage() {
  const central = useCentralOrcamentos()
  const navigate = useNavigate()
  const [filtro, setFiltro] = useState<Filtro>("todos")
  const hoje = hojeISO()

  const linhas = central.data ?? []
  const lista = useMemo(() => {
    switch (filtro) {
      case "com":
        return linhas.filter((l) => l.tem_orcamento)
      case "enviados":
        return linhas.filter((l) => l.tem_orcamento && l.enviado)
      case "sem":
        return linhas.filter((l) => !l.tem_orcamento)
      default:
        return linhas
    }
  }, [linhas, filtro])

  // resumo: soma só o que TEM orçamento (projetos sem versão não entram no total).
  const resumo = useMemo(() => {
    const comOrc = linhas.filter((l) => l.tem_orcamento)
    return {
      nComOrc: comOrc.length,
      nTotal: linhas.length,
      nEnviados: comOrc.filter((l) => l.enviado).length,
      totalPreco: comOrc.reduce((s, l) => s + l.preco_final, 0),
      totalCusto: comOrc.reduce((s, l) => s + l.custo_direto, 0),
    }
  }, [linhas])

  return (
    <div className="animate-fade-up">
      <div className="mb-6">
        <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Visão geral</div>
        <h1 className="font-word text-3xl leading-tight">Central de orçamentos</h1>
        <p className="mt-1 text-xs text-muted-foreground">
          Os orçamentos de todos os seus projetos num só lugar — a versão atual de cada um.
        </p>
      </div>

      {central.isLoading && <CenteredSpinner />}
      {central.isError && (
        <ErrorState
          message="Não foi possível carregar os orçamentos."
          onRetry={() => void central.refetch()}
        />
      )}

      {central.isSuccess && linhas.length === 0 && (
        <EmptyState
          icon={Calculator}
          title="Nenhum projeto ainda"
          description="Crie um projeto e monte o orçamento dele para vê-lo aqui."
        />
      )}

      {central.isSuccess && linhas.length > 0 && (
        <>
          {/* resumo */}
          <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <ResumoCard rotulo="Preço final (soma)" valor={formatBRL(resumo.totalPreco)} destaque />
            <ResumoCard rotulo="Custo direto (soma)" valor={formatBRL(resumo.totalCusto)} />
            <ResumoCard
              rotulo="Com orçamento"
              valor={`${resumo.nComOrc} de ${resumo.nTotal}`}
            />
            <ResumoCard rotulo="Enviados ao cliente" valor={String(resumo.nEnviados)} />
          </div>

          {/* filtro */}
          <div className="mb-4 flex flex-wrap gap-1.5">
            {FILTROS.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => setFiltro(f.key)}
                className={cn(
                  "rounded-full border px-3 py-1 text-xs transition-colors",
                  filtro === f.key
                    ? "border-primary bg-primary/10 text-foreground"
                    : "border-border text-muted-foreground hover:text-foreground",
                )}
              >
                {f.label}
              </button>
            ))}
          </div>

          {lista.length === 0 ? (
            <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
              Nenhum projeto neste filtro.
            </p>
          ) : (
            <Card className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted-foreground">
                      <th className="px-4 py-2.5 font-medium">Projeto</th>
                      <th className="px-3 py-2.5 font-medium">Versão</th>
                      <th className="px-3 py-2.5 font-medium">Situação</th>
                      <th className="px-3 py-2.5 font-medium">Validade</th>
                      <th className="px-3 py-2.5 text-right font-medium">Custo direto</th>
                      <th className="px-4 py-2.5 text-right font-medium">Preço final</th>
                      <th className="w-8" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {lista.map((l) => (
                      <LinhaProjeto key={l.projeto_id} l={l} hoje={hoje} navigate={navigate} />
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  )
}

function ResumoCard({
  rotulo,
  valor,
  destaque,
}: {
  rotulo: string
  valor: string
  destaque?: boolean
}) {
  return (
    <Card className="p-4">
      <div className="text-[11px] text-muted-foreground">{rotulo}</div>
      <div className={cn("mt-1 font-display text-xl", destaque ? "text-primary" : "text-foreground")}>
        {valor}
      </div>
    </Card>
  )
}

function LinhaProjeto({
  l,
  hoje,
  navigate,
}: {
  l: OrcamentoCentral
  hoje: string
  navigate: (to: string) => void
}) {
  const vencido = l.tem_orcamento && !!l.validade && l.validade < hoje
  const destino = `/projetos/${l.projeto_id}/orcamento`
  const ir = () => navigate(destino)
  return (
    <tr
      onClick={ir}
      className="cursor-pointer transition-colors hover:bg-accent/50"
      title="Abrir orçamento do projeto"
    >
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="font-display text-[11px] text-muted-foreground">
            #{l.projeto_seq ?? "—"}
          </span>
          {/* Link real = navegação por teclado/AT + ctrl-click p/ nova aba. stopPropagation evita o
              duplo-nav com o onClick do <tr> (e o ctrl-click não navegar a aba atual). */}
          <Link
            to={destino}
            onClick={(e) => e.stopPropagation()}
            className="break-words font-medium hover:text-primary focus-visible:underline focus-visible:outline-none"
          >
            {l.projeto_nome}
          </Link>
        </div>
      </td>
      <td className="px-3 py-3 text-muted-foreground">
        {l.tem_orcamento ? `R${l.numero}` : "—"}
      </td>
      <td className="px-3 py-3">
        {!l.tem_orcamento ? (
          <span className="text-xs text-muted-foreground">Sem orçamento</span>
        ) : l.enviado ? (
          <span className="inline-flex items-center gap-1 text-xs text-primary">
            <Send className="size-3" />
            Enviado
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">Rascunho</span>
        )}
      </td>
      <td className="px-3 py-3 text-xs">
        {l.tem_orcamento && l.validade ? (
          <span className={vencido ? "text-destructive" : "text-muted-foreground"}>
            {formatData(l.validade)}
            {vencido && " · vencido"}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </td>
      <td className="px-3 py-3 text-right text-muted-foreground">
        {l.tem_orcamento ? formatBRL(l.custo_direto) : "—"}
      </td>
      <td className="px-4 py-3 text-right font-medium">
        {l.tem_orcamento ? (
          formatBRL(l.preco_final)
        ) : (
          <span className="text-xs font-normal text-primary">Criar orçamento</span>
        )}
      </td>
      <td className="pr-3 text-muted-foreground">
        <ChevronRight className="size-4" />
      </td>
    </tr>
  )
}
