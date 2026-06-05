import { ArrowLeft } from "lucide-react"
import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"

import { Wordmark } from "@/components/brand/Wordmark"
import { CenteredSpinner } from "@/components/feedback/states"

// Defesa extra: remove blocos de citação que sejam ANOTAÇÕES INTERNAS para o advogado
// ("A CONFIRMAR COM ADVOGADO" / "RASCUNHO para revisão"). Os arquivos em /public/legal já vêm
// limpos, mas mantemos o filtro caso a fonte mude.
function semNotasInternas(md: string): string {
  const linhas = md.split(/\r?\n/)
  const saida: string[] = []
  let i = 0
  while (i < linhas.length) {
    if (linhas[i].trimStart().startsWith(">")) {
      const bloco: string[] = []
      while (i < linhas.length && linhas[i].trimStart().startsWith(">")) {
        bloco.push(linhas[i])
        i++
      }
      if (/A CONFIRMAR COM ADVOGADO|RASCUNHO para revis/i.test(bloco.join(" "))) continue
      saida.push(...bloco)
    } else {
      saida.push(linhas[i])
      i++
    }
  }
  return saida.join("\n")
}

const md: Components = {
  h1: ({ children }) => <h1 className="mt-8 text-2xl font-semibold text-foreground">{children}</h1>,
  h2: ({ children }) => (
    <h2 className="mt-8 border-t border-border pt-6 text-lg font-semibold text-foreground">
      {children}
    </h2>
  ),
  h3: ({ children }) => <h3 className="mt-6 font-semibold text-foreground">{children}</h3>,
  p: ({ children }) => <p className="mt-3 leading-relaxed text-muted-foreground">{children}</p>,
  ul: ({ children }) => (
    <ul className="mt-3 list-disc space-y-1.5 pl-5 text-muted-foreground">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-muted-foreground">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-primary underline underline-offset-2"
    >
      {children}
    </a>
  ),
  hr: () => <hr className="mt-8 border-border" />,
  blockquote: ({ children }) => (
    <blockquote className="mt-4 border-l-2 border-border pl-4 text-sm italic text-muted-foreground">
      {children}
    </blockquote>
  ),
  table: ({ children }) => (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border border-border bg-muted/40 p-2 text-left font-medium text-foreground">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-border p-2 align-top text-muted-foreground">{children}</td>
  ),
  code: ({ children }) => (
    <code className="rounded bg-muted px-1 py-0.5 text-[0.85em]">{children}</code>
  ),
}

export function LegalDocPage({
  arquivo,
  titulo,
  versao,
}: {
  arquivo: string
  titulo: string
  versao: string
}) {
  const [conteudo, setConteudo] = useState<string | null>(null)
  const [erro, setErro] = useState(false)

  useEffect(() => {
    document.title = `${titulo} — CRIA`
  }, [titulo])

  useEffect(() => {
    let vivo = true
    setConteudo(null)
    setErro(false)
    fetch(arquivo)
      .then((r) => {
        if (!r.ok) throw new Error("não encontrado")
        return r.text()
      })
      .then((t) => {
        // remove o H1 do próprio documento (já exibimos o título na página)
        if (vivo) setConteudo(semNotasInternas(t).replace(/^\s*#\s+.*\r?\n/, ""))
      })
      .catch(() => {
        if (vivo) setErro(true)
      })
    return () => {
      vivo = false
    }
  }, [arquivo])

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur-xl">
        <div className="mx-auto flex h-14 w-full max-w-3xl items-center justify-between px-5">
          <Wordmark className="text-lg" />
          <Link
            to="/login"
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-4" /> Voltar
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl px-5 pb-24 pt-6">
        <div className="rounded-xl border border-primary/40 bg-primary/10 px-4 py-3 text-xs text-foreground">
          <strong className="font-semibold">Versão preliminar ({versao}).</strong> Documento em
          revisão jurídica; a versão final pode mudar e um novo aceite poderá ser solicitado. Em caso
          de dúvida, fale conosco.
        </div>

        <h1 className="mt-6 text-2xl font-semibold">{titulo}</h1>

        {conteudo === null && !erro && (
          <div className="mt-10">
            <CenteredSpinner />
          </div>
        )}
        {erro && (
          <p className="mt-6 text-sm text-muted-foreground">
            Não foi possível carregar o documento agora. Tente novamente mais tarde.
          </p>
        )}
        {conteudo !== null && (
          <article className="text-sm">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={md}>
              {conteudo}
            </ReactMarkdown>
          </article>
        )}
      </main>
    </div>
  )
}
