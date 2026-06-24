import {
  Building2,
  ExternalLink,
  FolderKanban,
  Link2,
  Loader2,
  Mail,
  MessageCircle,
  MessageSquare,
  Pencil,
  Phone,
  Plus,
  Trash2,
  Unlink,
} from "lucide-react"
import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"
import { ApiError } from "@/lib/api"
import {
  ETAPAS,
  etapaMeta,
  useAtualizarOportunidade,
  useConverterOportunidade,
  useCriarProjetoDaOportunidade,
  useExcluirOportunidade,
  useVincularProjeto,
  type Oportunidade,
} from "@/features/comercial/comercialApi"
import { followupStatus, formatBRL, formatData, hojeISO } from "@/features/comercial/format"
import { ContextoSection } from "@/features/comercial/ContextoSection"

/** Monta o link wa.me (assume Brasil quando vier sem DDI). */
function whatsappHref(tel: string): string {
  const d = tel.replace(/\D/g, "")
  const full = d.startsWith("55") ? d : `55${d}`
  return `https://wa.me/${full}`
}

export function OportunidadeDetalheDialog({
  open,
  onOpenChange,
  oportunidade,
  onEditar,
  onComentarios,
  onVincularProjeto,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  oportunidade: Oportunidade | null
  onEditar: (op: Oportunidade) => void
  onComentarios: (op: Oportunidade) => void
  onVincularProjeto: (op: Oportunidade) => void
}) {
  const navigate = useNavigate()
  const atualizar = useAtualizarOportunidade()
  const converter = useConverterOportunidade()
  const excluir = useExcluirOportunidade()
  const criarProjeto = useCriarProjetoDaOportunidade()
  const vincular = useVincularProjeto()
  const [confirmando, setConfirmando] = useState(false)

  if (!oportunidade) return null
  const op = oportunidade
  const hoje = hojeISO()
  const fu = followupStatus(op.proximo_followup, hoje)
  // sugere o projeto a partir de "Visita" (índice 2 em ETAPAS), enquanto não houver projeto vinculado.
  const sugereProjeto = !op.projeto_id && ETAPAS.findIndex((e) => e.key === op.etapa) >= 2

  function mover(etapa: Oportunidade["etapa"]) {
    if (etapa === op.etapa) return
    atualizar.mutate({ id: op.id, patch: { etapa } })
  }

  async function onCriarProjeto() {
    try {
      const proj = await criarProjeto.mutateAsync(op)
      toast.success(`Projeto criado · #${proj.seq_humano ?? "—"}`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível criar o projeto.")
    }
  }

  async function onDesvincularProjeto() {
    try {
      await vincular.mutateAsync({ opId: op.id, projetoId: null })
      toast.success("Projeto desvinculado")
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível desvincular.")
    }
  }

  async function onConverter() {
    try {
      const obra = await converter.mutateAsync(op)
      toast.success(`Obra criada · #${obra.seq_humano ?? "—"}`)
      onOpenChange(false)
      navigate(`/obras/${obra.id}`)
    } catch (err) {
      if (err instanceof ApiError && err.isUpgrade) {
        toast.error(err.problem?.detail ?? "Limite do plano atingido.", {
          description: "Faça upgrade para criar mais obras ativas.",
        })
      } else {
        toast.error(err instanceof ApiError ? err.message : "Não foi possível criar a obra.")
      }
    }
  }

  async function onExcluir() {
    try {
      await excluir.mutateAsync(op.id)
      toast.success("Oportunidade excluída")
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível excluir.")
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) setConfirmando(false)
        onOpenChange(o)
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <span className="font-display text-sm text-muted-foreground">#{op.seq_humano ?? "—"}</span>
            <span
              className="rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide"
              style={{ background: etapaMeta(op.etapa).cor, color: "#1a1505" }}
            >
              {etapaMeta(op.etapa).label}
            </span>
          </div>
          <DialogTitle className="break-words">{op.nome}</DialogTitle>
          <DialogDescription>Toque numa etapa para mover no funil.</DialogDescription>
        </DialogHeader>

        <div className="-mx-1 flex max-h-[60vh] flex-col gap-5 overflow-y-auto px-1">
          {/* mover etapa (stepper poka-yoke) */}
          <div className="flex flex-wrap gap-1.5">
            {ETAPAS.map((et) => {
              const ativo = op.etapa === et.key
              return (
                <button
                  key={et.key}
                  type="button"
                  onClick={() => mover(et.key)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                    ativo
                      ? "border-transparent"
                      : "border-border text-muted-foreground hover:text-foreground",
                  )}
                  style={ativo ? { background: et.cor, color: "#1a1505" } : undefined}
                >
                  {et.label}
                </button>
              )
            })}
          </div>

          {/* comentários (acesso rápido — abre a folha de timeline) */}
          <button
            type="button"
            onClick={() => onComentarios(op)}
            className="flex items-center justify-between rounded-xl border border-border bg-card px-3 py-2 text-sm transition-colors hover:border-primary/40"
          >
            <span className="flex items-center gap-2">
              <MessageSquare className="size-4 text-muted-foreground" />
              Comentários
            </span>
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
              {op.comentarios_count}
            </span>
          </button>

          {/* ações de contato */}
          {(op.contato_telefone || op.contato_email) && (
            <div className="flex flex-wrap gap-2">
              {op.contato_telefone && (
                <>
                  <Button asChild variant="outline" size="sm">
                    <a href={whatsappHref(op.contato_telefone)} target="_blank" rel="noreferrer">
                      <MessageCircle />
                      WhatsApp
                    </a>
                  </Button>
                  <Button asChild variant="outline" size="sm">
                    <a href={`tel:${op.contato_telefone}`}>
                      <Phone />
                      Ligar
                    </a>
                  </Button>
                </>
              )}
              {op.contato_email && (
                <Button asChild variant="outline" size="sm">
                  <a href={`mailto:${op.contato_email}`}>
                    <Mail />
                    E-mail
                  </a>
                </Button>
              )}
            </div>
          )}

          {/* dados */}
          <dl className="space-y-2.5 text-sm">
            <Linha rotulo="Contato" valor={op.contato_nome} />
            <Linha rotulo="Telefone" valor={op.contato_telefone} />
            <Linha rotulo="E-mail" valor={op.contato_email} />
            <Linha rotulo="Origem" valor={op.origem} />
            <Linha
              rotulo="Valor estimado"
              valor={op.valor_estimado != null ? formatBRL(op.valor_estimado) : null}
            />
            <div className="flex items-start justify-between gap-3">
              <dt className="shrink-0 text-muted-foreground">Próximo follow-up</dt>
              <dd className="text-right">
                {op.proximo_followup ? (
                  <span
                    className={cn(
                      "font-medium",
                      fu === "atrasado" && "text-destructive",
                      fu === "hoje" && "text-primary",
                    )}
                  >
                    {formatData(op.proximo_followup)}
                    {fu === "atrasado" && " · atrasado"}
                    {fu === "hoje" && " · hoje"}
                  </span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </dd>
            </div>
          </dl>

          {op.observacoes && (
            <div className="space-y-1">
              <div className="text-xs uppercase tracking-wide text-muted-foreground">Observações</div>
              <p className="whitespace-pre-wrap break-words text-sm">{op.observacoes}</p>
            </div>
          )}

          {/* contexto do cliente (memória do agente de lembretes) */}
          <ContextoSection opId={op.id} open={open} />

          {/* projeto (costura lead → projeto; sugerido a partir de Visita) */}
          <div
            className={cn(
              "rounded-xl border p-3",
              sugereProjeto ? "border-primary/50 bg-primary/5" : "border-border",
            )}
          >
            <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
              <FolderKanban className="size-3.5" />
              Projeto
            </div>
            {op.projeto_id ? (
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="outline" size="sm">
                  <Link to={`/projetos/${op.projeto_id}`}>
                    <ExternalLink />
                    Ver projeto
                  </Link>
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={vincular.isPending}
                  onClick={onDesvincularProjeto}
                >
                  <Unlink />
                  Desvincular
                </Button>
              </div>
            ) : (
              <>
                {sugereProjeto && (
                  <p className="mb-2 text-xs text-foreground">
                    Hora de criar o projeto deste cliente.
                  </p>
                )}
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" disabled={criarProjeto.isPending} onClick={onCriarProjeto}>
                    {criarProjeto.isPending ? <Loader2 className="animate-spin" /> : <Plus />}
                    Criar projeto
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => onVincularProjeto(op)}>
                    <Link2 />
                    Vincular existente
                  </Button>
                </div>
              </>
            )}
          </div>

          {/* conversão em obra */}
          {op.obra_id ? (
            <Button asChild variant="outline">
              <Link to={`/obras/${op.obra_id}`}>
                <ExternalLink />
                Ver obra vinculada
              </Link>
            </Button>
          ) : op.etapa === "ganho" ? (
            <Button onClick={onConverter} disabled={converter.isPending}>
              {converter.isPending ? <Loader2 className="animate-spin" /> : <Building2 />}
              Criar obra a partir desta oportunidade
            </Button>
          ) : (
            <p className="text-xs text-muted-foreground">
              Marque a etapa como <span className="font-medium text-foreground">Ganho</span> para
              gerar a obra.
            </p>
          )}
        </div>

        {/* rodapé: editar / excluir (confirmação inline — evita 2 modais empilhados) */}
        {confirmando ? (
          <div className="flex items-center gap-2 rounded-xl border border-destructive/40 bg-destructive/5 p-2">
            <span className="px-1 text-sm">Excluir esta oportunidade?</span>
            <div className="ml-auto flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setConfirmando(false)}>
                Cancelar
              </Button>
              <Button
                variant="destructive"
                size="sm"
                disabled={excluir.isPending}
                onClick={onExcluir}
              >
                {excluir.isPending && <Loader2 className="animate-spin" />}
                Excluir
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex gap-2">
            <Button variant="outline" className="flex-1" onClick={() => onEditar(op)}>
              <Pencil />
              Editar
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Excluir"
              title="Excluir"
              onClick={() => setConfirmando(true)}
            >
              <Trash2 className="text-destructive" />
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function Linha({ rotulo, valor }: { rotulo: string; valor: string | null }) {
  if (!valor) return null
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-muted-foreground">{rotulo}</dt>
      <dd className="break-words text-right font-medium">{valor}</dd>
    </div>
  )
}
