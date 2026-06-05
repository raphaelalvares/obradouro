import { Navigate, Outlet } from "react-router-dom"

import { useAuth } from "@/auth/AuthProvider"
import { CenteredSpinner } from "@/components/feedback/states"
import { AceiteGate } from "@/features/auth/AceiteGate"

export function ProtectedRoute() {
  const { session, loading } = useAuth()
  if (loading) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <CenteredSpinner />
      </div>
    )
  }
  if (!session) return <Navigate to="/login" replace />
  return (
    <AceiteGate>
      <Outlet />
    </AceiteGate>
  )
}
