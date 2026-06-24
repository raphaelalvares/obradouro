import { Brain, Loader2, Pencil } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { ApiError } from "@/lib/api"
import {
  useContexto,
  useSalvarContexto,
  type CanalPreferido,
  type ContextoPerfil,
} from "@/features/comercial/contextoApi"

const CANAIS: { v: CanalPreferido; label: string }[] = [
  { v: "whatsapp", label: "WhatsApp" },
  { v: "telefone", label: "Telefone" },
  { v: "email", label: "E-mail" },
]
const CANAL_LABEL: Record<CanalPreferido, string> = {
  whatsapp: "WhatsApp",
  telefone: "Telefone",
  email: "E-mail",
}
const RESUMO_MAX = 600

const temConteudo = (perfil: ContextoPerfil, resumo: string | null): boolean =>
  Boolean(resumo) || Object.values(perfil).some((v) => v != null && v !== "")

/** Cartão de contexto do cliente (memória do agente): perfil estruturado + resumo curto, editáveis.
 * Só busca quando o modal está aberto. Degrada se a migration 0087 ainda não foi aplicada (o backend
 * devolve existe=false na leitura). */
export function ContextoSection({ opId, open }: { opId: string; open: boolean }) {
  const q = useContexto(opId, open)
  const salvar = useSalvarContexto(opId)
  const [editando, setEditando] = useState(false)
  const [perfil, setPerfil] = useState<ContextoPerfil>({})
  const [resumo, setResumo] = useState("")

  // hidrata o form quando os dados chegam / muda de oportunidade.
  useEffect(() => {
    if (q.data) {
      setPerfil(q.data.perfil ?? {})
      setResumo(q.data.resumo ?? "")
      setEditando(false)
    }
  }, [q.data, opId])

  async function onSalvar() {
    try {
      await salvar.mutateAsync({ perfil, resumo: resumo.trim() || null })
      toast.success("Contexto salvo")
      setEditando(false)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Não foi possível salvar o contexto.")
    }
  }

  function onCancelar() {
    setPerfil(q.data?.perfil ?? {})
    setResumo(q.data?.resumo ?? "")
    setEditando(false)
  }

  const cheio = temConteudo(q.data?.perfil ?? {}, q.data?.resumo ?? null)

  return (
    <div className="rounded-xl border border-border p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
          <Brain className="size-3.5" />
          Contexto do cliente
        </span>
        {!editando && q.isSuccess && (
          <Button variant="ghost" size="sm" onClick={() => setEditando(true)}>
            <Pencil />
            {cheio ? "Editar" : "Adicionar"}
          </Button>
        )}
      </div>

      {q.isLoading && <Loader2 className="size-4 animate-spin text-muted-foreground" />}

      {!editando &&
        q.isSuccess &&
        (cheio ? (
          <div className="space-y-2 text-sm">
            {q.data?.resumo && <p className="whitespace-pre-wrap break-words">{q.data.resumo}</p>}
            <PerfilChips perfil={q.data?.perfil ?? {}} />
          </div>
        ) : (
          <p className="text-xs text-muted-foreground">
            Sem contexto ainda. Anote preferências e o histórico do cliente para os lembretes ficarem
            mais úteis.
          </p>
        ))}

      {editando && (
        <div className="space-y-3">
          <div>
            <Label htmlFor="ctx-resumo">Resumo</Label>
            <Textarea
              id="ctx-resumo"
              value={resumo}
              maxLength={RESUMO_MAX}
              onChange={(e) => setResumo(e.target.value)}
              placeholder="Onde a relação está, o que o cliente espera, próximo passo…"
              className="mt-1 min-h-[72px]"
            />
            <p className="mt-1 text-right text-[10px] text-muted-foreground">
              {resumo.length}/{RESUMO_MAX}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <Label>Canal preferido</Label>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {CANAIS.map((c) => {
                  const ativo = perfil.canal_preferido === c.v
                  return (
                    <button
                      key={c.v}
                      type="button"
                      onClick={() =>
                        setPerfil((p) => ({ ...p, canal_preferido: ativo ? null : c.v }))
                      }
                      className={cn(
                        "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                        ativo
                          ? "border-primary bg-primary/10 text-foreground"
                          : "border-border text-muted-foreground hover:text-foreground",
                      )}
                    >
                      {c.label}
                    </button>
                  )
                })}
              </div>
            </div>
            <div>
              <Label htmlFor="ctx-horario">Melhor horário</Label>
              <Input
                id="ctx-horario"
                value={perfil.melhor_horario ?? ""}
                maxLength={80}
                onChange={(e) => setPerfil((p) => ({ ...p, melhor_horario: e.target.value }))}
                placeholder="ex.: tardes"
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="ctx-cadencia">Cadência (dias)</Label>
              <Input
                id="ctx-cadencia"
                type="number"
                min={1}
                max={365}
                value={perfil.cadencia_dias ?? ""}
                onChange={(e) =>
                  setPerfil((p) => ({
                    ...p,
                    cadencia_dias: e.target.value ? Number(e.target.value) : null,
                  }))
                }
                placeholder="ex.: 7"
                className="mt-1"
              />
            </div>
            <div className="col-span-2">
              <Label htmlFor="ctx-decisor">Quem decide</Label>
              <Input
                id="ctx-decisor"
                value={perfil.decisor ?? ""}
                maxLength={120}
                onChange={(e) => setPerfil((p) => ({ ...p, decisor: e.target.value }))}
                placeholder="ex.: a esposa decide"
                className="mt-1"
              />
            </div>
            <label className="col-span-2 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={perfil.sensivel_a_preco ?? false}
                onChange={(e) => setPerfil((p) => ({ ...p, sensivel_a_preco: e.target.checked }))}
                className="size-4 rounded border-input"
              />
              Sensível a preço
            </label>
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="outline" size="sm" onClick={onCancelar}>
              Cancelar
            </Button>
            <Button size="sm" disabled={salvar.isPending} onClick={onSalvar}>
              {salvar.isPending && <Loader2 className="animate-spin" />}
              Salvar
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

function PerfilChips({ perfil }: { perfil: ContextoPerfil }) {
  const chips: string[] = []
  if (perfil.canal_preferido) chips.push(CANAL_LABEL[perfil.canal_preferido])
  if (perfil.melhor_horario) chips.push(perfil.melhor_horario)
  if (perfil.cadencia_dias) chips.push(`cada ${perfil.cadencia_dias}d`)
  if (perfil.decisor) chips.push(perfil.decisor)
  if (perfil.sensivel_a_preco) chips.push("sensível a preço")
  if (chips.length === 0) return null
  return (
    <div className="flex flex-wrap gap-1.5">
      {chips.map((c) => (
        <span key={c} className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          {c}
        </span>
      ))}
    </div>
  )
}
