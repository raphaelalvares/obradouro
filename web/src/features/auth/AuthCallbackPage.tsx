import { useEffect, useState } from "react"
import { Navigate, useSearchParams } from "react-router-dom"

import { useAuth } from "@/auth/AuthProvider"
import { CenteredSpinner } from "@/components/feedback/states"

// Destino do redirect do OAuth (e do link de confirmação de e-mail). O cliente Supabase
// (detectSessionInUrl) processa a URL e dispara SIGNED_IN; aqui só esperamos a sessão e seguimos.
export function AuthCallbackPage() {
  const { session, loading } = useAuth()
  const [params] = useSearchParams()
  const [expirou, setExpirou] = useState(false)

  // Erro do provedor pode vir na query (?error=) ou no fragmento (#error=).
  const hash = typeof window !== "undefined" ? window.location.hash : ""
  const houveErro = Boolean(params.get("error")) || hash.includes("error=")

  useEffect(() => {
    const t = setTimeout(() => setExpirou(true), 8000)
    return () => clearTimeout(t)
  }, [])

  if (houveErro) return <Navigate to="/login?erro=oauth" replace />
  if (!loading && session) return <Navigate to="/" replace />
  if (expirou && !session) return <Navigate to="/login?erro=oauth" replace />

  return (
    <div className="grid min-h-dvh place-items-center">
      <CenteredSpinner />
    </div>
  )
}
