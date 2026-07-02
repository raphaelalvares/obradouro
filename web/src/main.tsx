import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { Toaster } from "sonner"

import { App } from "@/app/App"
import { AuthProvider } from "@/auth/AuthProvider"
// Tipografia do protótipo (pré-rebrand), agora self-hosted (sem CDN do Google) p/ respeitar a CSP
// font-src 'self': Oswald (display: títulos, leve/tracking largo, 200–500) e Outfit (corpo/UI,
// 300–600). Os nomes de família "Oswald"/"Outfit" batem com o tailwind.config.
import "@fontsource/oswald/200.css"
import "@fontsource/oswald/300.css"
import "@fontsource/oswald/400.css"
import "@fontsource/oswald/500.css"
import "@fontsource/outfit/300.css"
import "@fontsource/outfit/400.css"
import "@fontsource/outfit/500.css"
import "@fontsource/outfit/600.css"
// Montserrat = fonte do WORDMARK (nome nominativo do logo). Só a marca usa (font-wordmark); títulos
// e corpo seguem Oswald/Outfit.
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
