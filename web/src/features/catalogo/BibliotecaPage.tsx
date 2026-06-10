import { useState, type ReactNode } from "react"

import { cn } from "@/lib/utils"
import { CatalogoPage } from "@/features/catalogo/CatalogoPage"
import { TemplatesPage } from "@/features/catalogo/TemplatesPage"

export function BibliotecaPage() {
  const [aba, setAba] = useState<"servicos" | "templates">("servicos")
  return (
    <div className="animate-fade-up">
      <div className="mb-4">
        <div className="text-[10px] uppercase tracking-[0.3em] text-primary">Livro de referências</div>
        <h1 className="font-word text-4xl leading-none">BIBLIOTECA</h1>
      </div>

      <div className="mb-4 inline-flex rounded-xl border border-border p-1">
        <AbaBtn ativo={aba === "servicos"} onClick={() => setAba("servicos")}>
          Serviços
        </AbaBtn>
        <AbaBtn ativo={aba === "templates"} onClick={() => setAba("templates")}>
          Templates de ambiente
        </AbaBtn>
      </div>

      {aba === "servicos" ? <CatalogoPage /> : <TemplatesPage />}
    </div>
  )
}

function AbaBtn({
  ativo,
  onClick,
  children,
}: {
  ativo: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
        ativo ? "bg-primary/10 text-foreground" : "text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  )
}
