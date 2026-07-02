import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { Toaster } from "sonner"

import { App } from "@/app/App"
import { AuthProvider } from "@/auth/AuthProvider"
// Identidade Obra D'Ouro: fontes self-hosted (sem CDN do Google) do manual de marca —
// Poppins (display: títulos/branding, 300–700, geométrica e arredondada — casa com a logo) e Inter
// (corpo/UI, 300–600). Os nomes de família "Poppins"/"Inter" batem com o tailwind.config. Sem
// dependência de fonts.googleapis/gstatic em runtime → a CSP segue em font-src 'self'.
import "@fontsource/poppins/300.css"
import "@fontsource/poppins/400.css"
import "@fontsource/poppins/500.css"
import "@fontsource/poppins/600.css"
import "@fontsource/poppins/700.css"
import "@fontsource/inter/300.css"
import "@fontsource/inter/400.css"
import "@fontsource/inter/500.css"
import "@fontsource/inter/600.css"
// Montserrat = fonte do WORDMARK (nome nominativo), geométrica e mais larga — casa com o traço da
// logo. Títulos/UI seguem Poppins/Inter; a Montserrat entra só na marca (font-wordmark).
import "@fontsource/montserrat/500.css"
import "@fontsource/montserrat/600.css"
import "@/index.css"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false },
  },
})

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <App />
        <Toaster
          position="top-center"
          theme="dark"
          toastOptions={{
            classNames: {
              toast: "!bg-popover !border-border !text-foreground !rounded-xl",
              description: "!text-muted-foreground",
              actionButton: "!bg-primary !text-primary-foreground",
            },
          }}
        />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
)
