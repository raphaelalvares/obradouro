import { Navigate } from "react-router-dom"

import { CenteredSpinner } from "@/components/feedback/states"

import { useIsAdmin } from "./adminApi"

/** Gate da rota /admin: só o dono da plataforma entra. Não-admin → manda pra home. */
export function AdminRoute({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useIsAdmin()
  if (isLoading) return <CenteredSpinner />
  if (!data?.is_admin) return <Navigate to="/" replace />
  return <>{children}</>
}
