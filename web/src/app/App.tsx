import { lazy, Suspense } from "react"
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/app/AppShell"
import { ProtectedRoute } from "@/app/ProtectedRoute"
import { CenteredSpinner } from "@/components/feedback/states"
import { AuthCallbackPage } from "@/features/auth/AuthCallbackPage"
import { CadastroPage } from "@/features/auth/CadastroPage"
import { LoginPage } from "@/features/auth/LoginPage"
import { CronogramaPage } from "@/features/checklist/CronogramaPage"
import { GanttPage } from "@/features/checklist/GanttPage"

// Páginas legais carregam react-markdown — lazy p/ não pesar o bundle inicial (só /termos e /privacidade).
const LegalDocPage = lazy(() =>
  import("@/features/legal/LegalDocPage").then((m) => ({ default: m.LegalDocPage })),
)

// Versão vigente dos documentos legais — espelha backend app/core/legal.py (DOCUMENTOS).
const VERSAO_LEGAL = "2026-06-04"
import { CatalogoPage } from "@/features/catalogo/CatalogoPage"
import { ComercialPage } from "@/features/comercial/ComercialPage"
import { ConfiguracoesPage } from "@/features/conta/ConfiguracoesPage"
import { EstoquePage } from "@/features/estoque/EstoquePage"
import { ObraHubPage } from "@/features/obras/ObraHubPage"
import { ObrasPage } from "@/features/obras/ObrasPage"
import { OrcamentoPage } from "@/features/orcamento/OrcamentoPage"
import { MoodboardPage } from "@/features/projetos/MoodboardPage"
import { ProjetoHubPage } from "@/features/projetos/ProjetoHubPage"
import { ProjetosPage } from "@/features/projetos/ProjetosPage"
import { RevisoesPage } from "@/features/projetos/RevisoesPage"

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/cadastro" element={<CadastroPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route
          path="/termos"
          element={
            <Suspense fallback={<RotaCarregando />}>
              <LegalDocPage arquivo="/legal/termos.md" titulo="Termos de Uso" versao={VERSAO_LEGAL} />
            </Suspense>
          }
        />
        <Route
          path="/privacidade"
          element={
            <Suspense fallback={<RotaCarregando />}>
              <LegalDocPage
                arquivo="/legal/privacidade.md"
                titulo="Política de Privacidade"
                versao={VERSAO_LEGAL}
              />
            </Suspense>
          }
        />
        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route index element={<ObrasPage />} />
            <Route path="obras/:obraId" element={<ObraHubPage />} />
            <Route path="obras/:obraId/cronograma" element={<CronogramaPage />} />
            <Route path="obras/:obraId/cronograma/gantt" element={<GanttPage />} />
            <Route path="obras/:obraId/estoque" element={<EstoquePage />} />
            <Route path="comercial" element={<ComercialPage />} />
            <Route path="biblioteca" element={<CatalogoPage />} />
            <Route path="projetos" element={<ProjetosPage />} />
            <Route path="projetos/:projetoId" element={<ProjetoHubPage />} />
            <Route path="projetos/:projetoId/moodboard" element={<MoodboardPage />} />
            <Route path="projetos/:projetoId/revisoes" element={<RevisoesPage />} />
            <Route path="projetos/:projetoId/orcamento" element={<OrcamentoPage />} />
            <Route path="configuracoes" element={<ConfiguracoesPage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

function RotaCarregando() {
  return (
    <div className="grid min-h-dvh place-items-center">
      <CenteredSpinner />
    </div>
  )
}
