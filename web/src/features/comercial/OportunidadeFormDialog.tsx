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
  ETAPAS,
  useAtualizarOportunidade,
  useCriarOportunidade,
  type EtapaOportunidade,
  type Oportunidade,
  type OportunidadeForm,
} from "@/features/comercial/comercialApi"
import { parseValor } from "@/features/comercial/format"

const MAX_NOME = 200

function trimOrNull(s: string): string | null {
  const t = s.trim()
  return t ? t : null
}
function valorParaInput(n: number | null): string {
  return n == null ? "" : String(n).replace(".", ",")
}

export function OportunidadeFormDialog({
  open,
  onOpenChange,
  oportunidade,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** presente = edição; ausente = criação. */
  oportunidade?: Oportunidade | null
}) {
  const editando = !!oportunidade
  const [nome, setNome] = useState("")
  const [etapa, setEtapa] = useState<EtapaOportunidade>("lead")
  const [contatoNome, setContatoNome] = useState("")
  const [telefone, setTelefone] = useState("")
  const [email, setEmail] = useState("")
  const [origem, setOrigem] = useState("")
  const [valor, setValor] = useState("")
  const [followup, setFollowup] = useState("")
  const [obs, setObs] = useState("")

  const criar = useCriarOportunidade()
  const atualizar = useAtualizarOportunidade()
  const salvando = criar.isPending || atualizar.isPending
  const valido = nome.trim().length > 0

  // Preenche o formulário ao abrir (edição) ou zera (criação). Depende de `open` p/ resetar a cada abertura.
  useEffect(() => {
    if (!open) return
    setNome(oportunidade?.nome ?? "")
    setEtapa(oportunidade?.etapa ?? "lead")
    setContatoNome(oportunidade?.contato_nome ?? "")
    setTelefone(oportunidade?.contato_telefone ?? "")
    setEmail(oportunidade?.contato_email ?? "")
    setOrigem(oportunidade?.origem ?? "")
    setValor(valorParaInput(oportunidade?.valor_estimado ?? null))
    setFollowup(oportunidade?.proximo_followup ?? "")
    setObs(oportunidade?.observacoes ?? "")
  }, [open, oportunidade])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (!valido || salvando) return
    const payload: OportunidadeForm = {
      nome: nome.trim(),
      etapa,
      contato_nome: trimOrNull(contatoNome),
      contato_telefone: trimOrNull(telefone),
      contato_email: trimOrNull(email),
      origem: trimOrNull(origem),
      valor_estimado: parseValor(valor),
      proximo_followup: followup || null,
      observacoes: trimOrNull(obs),
    }
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

            <div className="space-y-1.5">
              <Label>Etapa</Label>
              <div className="flex flex-wrap gap-1.5">
                {ETAPAS.map((et) => {
                  const ativo = etapa === et.key
                  return (
                    <button
                      key={et.key}
                      type="button"
                      onClick={() => setEtapa(et.key)}
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
            </div>

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

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="op-valor">Valor estimado</Label>
                <Input
                  id="op-valor"
                  inputMode="decimal"
                  value={valor}
                  onChange={(e) => setValor(e.target.value)}
                  placeholder="R$ 0,00"
                />
              </div>
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
