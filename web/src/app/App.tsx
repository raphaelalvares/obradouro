import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/app/AppShell"
import { ProtectedRoute } from "@/app/ProtectedRoute"
import { LoginPage } from "@/features/auth/LoginPage"
import { CronogramaPage } from "@/features/checklist/CronogramaPage"
import { ConfiguracoesPage } from "@/features/conta/ConfiguracoesPage"
import { EstoquePage } from "@/features/estoque/EstoquePage"
import { ObraHubPage } from "@/features/obras/ObraHubPage"
import { ObrasPage } from "@/features/obras/ObrasPage"
import { MoodboardPage } from "@/features/projetos/MoodboardPage"
import { ProjetoHubPage } from "@/features/projetos/ProjetoHubPage"
import { ProjetosPage } from "@/features/projetos/ProjetosPage"
import { RevisoesPage } from "@/features/projetos/RevisoesPage"

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route index element={<ObrasPage />} />
            <Route path="obras/:obraId" element={<ObraHubPage />} />
            <Route path="obras/:obraId/cronograma" element={<CronogramaPage />} />
            <Route path="obras/:obraId/estoque" element={<EstoquePage />} />
            <Route path="projetos" element={<ProjetosPage />} />
            <Route path="projetos/:projetoId" element={<ProjetoHubPage />} />
            <Route path="projetos/:projetoId/moodboard" element={<MoodboardPage />} />
            <Route path="projetos/:projetoId/revisoes" element={<RevisoesPage />} />
            <Route path="configuracoes" element={<ConfiguracoesPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
