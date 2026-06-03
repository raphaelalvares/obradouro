import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/app/AppShell"
import { ProtectedRoute } from "@/app/ProtectedRoute"
import { LoginPage } from "@/features/auth/LoginPage"
import { ObraDetailPage } from "@/features/checklist/ObraDetailPage"
import { ObrasPage } from "@/features/obras/ObrasPage"

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route index element={<ObrasPage />} />
            <Route path="obras/:obraId" element={<ObraDetailPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
