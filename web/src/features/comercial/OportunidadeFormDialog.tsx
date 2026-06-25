import { Loader2 } from "lucide-react"
import { useEffect, useState, type FormEvent } from "react"
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
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { ApiError } from "@/lib/api"
import {
  useAtualizarOportunidade,
  useCriarOportunidade,
  type FunilKey,
  type Oportunidade,
  type OportunidadeForm,
} from "@/features/comercial/comercialApi"
import { maskValorBRL, parseValor } from "@/features/comercial/format"

const MAX_NOME = 200
type Escopo = "projeto" | "obra" | "ambos"
const ESCOPOS: { key: Escopo; label: string }[] = [
  { key: "projeto", label: "Projeto" },
  { key: "obra", label: "Obra" },
  { key: "ambos", label: "Ambos" },
]

function trimOrNull(s: string): string | null {
  const t = s.trim()
  return t ? t : null
}
function valorParaInput(n: number | null): string {
  return n == null ? "" : maskValorBRL(String(Math.round(n * 100)))
}

export function OportunidadeFormDialog({
  open,
  onOpenChange,
  oportunidade,
  funilPadrao,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** presente = edição; ausente = criação. */
  oportunidade?: Oportunidade | null
  /** funil ativo na página — define o "Entra como" padrão ao criar. */
  funilPadrao?: FunilKey
}) {
  const editando = !!oportunidade
  const [nome, setNome] = useState("")
  const [escopo, setEscopo] = useState<Escopo>("projeto")
  const [contatoNome, setContatoNome] = useState("")
  const [telefone, setTelefone] = useState("")
  const [email, setEmail] = useState("")
  const [origem, setOrigem] = useState("")
  const [valorProjeto, setValorProjeto] = useState("")
  const [valorObra, setValorObra] = useState("")
  const [followup, setFollowup] = useState("")
  const [obs, setObs] = useState("")

  const criar = useCriarOportunidade()
  const atualizar = useAtualizarOportunidade()
  const salvando = criar.isPending || atualizar.isPending
  const valido = nome.trim().length > 0

  // quais funis o card abrange: na edição vem da posse do card; na criação, do "Entra como".
  const incluiProjeto = editando ? oportunidade!.etapa != null : escopo !== "obra"
  const incluiObra = editando ? oportunidade!.etapa_obra != null : escopo !== "projeto"

  // Preenche o formulário ao abrir (edição) ou zera (criação). Depende de `open` p/ resetar a cada abertura.
  useEffect(() => {
    if (!open) return
    setNome(oportunidade?.nome ?? "")
    setEscopo(funilPadrao === "obra" ? "obra" : "projeto")
    setContatoNome(oportunidade?.contato_nome ?? "")
    setTelefone(oportunidade?.contato_telefone ?? "")
    setEmail(oportunidade?.contato_email ?? "")
    setOrigem(oportunidade?.origem ?? "")
    setValorProjeto(valorParaInput(oportunidade?.valor_estimado ?? null))
    setValorObra(valorParaInput(oportunidade?.valor_obra ?? null))
    setFollowup(oportunidade?.proximo_followup ?? "")
    setObs(oportunidade?.observacoes ?? "")
  }, [open, oportunidade, funilPadrao])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || salvando) return
    const payload: OportunidadeForm = {
      nome: nome.trim(),
      contato_nome: trimOrNull(contatoNome),
      contato_telefone: trimOrNull(telefone),
      contato_email: trimOrNull(email),
      origem: trimOrNull(origem),
      proximo_followup: followup || null,
      observacoes: trimOrNull(obs),
    }
    // na CRIAÇÃO, o "Entra como" define as etapas iniciais de cada funil (poka-yoke: começa no início).
    if (!editando) {
      payload.etapa = incluiProjeto ? "lead" : null
      payload.etapa_obra = incluiObra ? "a_orcar" : null
    }
    if (incluiProjeto) payload.valor_estimado = parseValor(valorProjeto)
    if (incluiObra) payload.valor_obra = parseValor(valorObra)
    try {
      if (editando && oportunidade) {
        await atualizar.mutateAsync({ id: oportunidade.id, patch: payload })
        toast.success("Oportunidade atualizada")
      } else {
        const nova = await criar.mutateAsync(payload)
        toast.success(`Oportunidade criada · #${nova.seq_humano ?? "—"}`)
      }
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar a oportunidade.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{editando ? "Editar oportunidade" : "Nova oportunidade"}</DialogTitle>
          <DialogDescription>
            {editando
              ? "Atualize os dados de follow-up."
              : "Cadastre o lead — o número é atribuído automaticamente."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={onSubmit} className="flex min-h-0 flex-col gap-4" noValidate>
          <div className="-mx-1 max-h-[58vh] space-y-4 overflow-y-auto px-1">
            <div className="space-y-1.5">
              <Label htmlFor="op-nome">Oportunidade *</Label>
              <Input
                id="op-nome"
                required
                maxLength={MAX_NOME}
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                placeholder="Ex.: Reforma Apto 302 — Ana"
              />
            </div>

            {/* "Entra como" — só na criação; define em qual(is) funil(is) o lead entra (poka-yoke) */}
            {!editando && (
              <div className="space-y-1.5">
                <Label>Entra como</Label>
                <div className="flex flex-wrap gap-1.5">
                  {ESCOPOS.map((es) => {
                    const ativo = escopo === es.key
                    return (
                      <button
                        key={es.key}
                        type="button"
                        onClick={() => setEscopo(es.key)}
                        className={cn(
                          "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                          ativo
                            ? "border-transparent bg-primary text-primary-foreground"
                            : "border-border text-muted-foreground hover:text-foreground",
                        )}
                      >
                        {es.label}
                      </button>
                    )
                  })}
                </div>
                <p className="text-xs text-muted-foreground">
                  {escopo === "projeto"
                    ? "Vai vender o projeto de arquitetura."
                    : escopo === "obra"
                      ? "Já tem projeto — entra direto na conversão para obra."
                      : "Acompanha as duas trilhas (projeto e obra)."}
                </p>
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="op-contato">Contato</Label>
              <Input
                id="op-contato"
                value={contatoNome}
                onChange={(e) => setContatoNome(e.target.value)}
                placeholder="Nome do cliente"
              />
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="op-tel">WhatsApp / telefone</Label>
                <Input
                  id="op-tel"
                  type="tel"
                  inputMode="tel"
                  value={telefone}
                  onChange={(e) => setTelefone(e.target.value)}
                  placeholder="(11) 99999-9999"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="op-email">E-mail</Label>
                <Input
                  id="op-email"
                  type="email"
                  inputMode="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="cliente@email.com"
                />
              </div>
            </div>

            {/* valores por funil — só os campos do(s) funil(is) do card */}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {incluiProjeto && (
                <div className="space-y-1.5">
                  <Label htmlFor="op-valor-proj">Valor do projeto</Label>
                  <Input
                    id="op-valor-proj"
                    inputMode="numeric"
                    value={valorProjeto}
                    onChange={(e) => setValorProjeto(maskValorBRL(e.target.value))}
                    placeholder="R$ 0,00"
                  />
                </div>
              )}
              {incluiObra && (
                <div className="space-y-1.5">
                  <Label htmlFor="op-valor-obra">Valor da obra</Label>
                  <Input
                    id="op-valor-obra"
                    inputMode="numeric"
                    value={valorObra}
                    onChange={(e) => setValorObra(maskValorBRL(e.target.value))}
                    placeholder="R$ 0,00"
                  />
                </div>
              )}
              <div className="space-y-1.5">
                <Label htmlFor="op-followup">Próximo follow-up</Label>
                <Input
                  id="op-followup"
                  type="date"
                  value={followup}
                  onChange={(e) => setFollowup(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="op-origem">Origem</Label>
              <Input
                id="op-origem"
                value={origem}
                onChange={(e) => setOrigem(e.target.value)}
                placeholder="Indicação, Instagram, site…"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="op-obs">Observações</Label>
              <Textarea
                id="op-obs"
                value={obs}
                onChange={(e) => setObs(e.target.value)}
                placeholder="Anotações do acompanhamento…"
              />
            </div>
          </div>

          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              className="flex-1"
              onClick={() => onOpenChange(false)}
            >
              Cancelar
            </Button>
            <Button type="submit" className="flex-1" disabled={!valido || salvando}>
              {salvando && <Loader2 className="animate-spin" />}
              {editando ? "Salvar" : "Criar"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
