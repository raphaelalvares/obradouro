import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { Toaster } from "sonner"

import { App } from "@/app/App"
import { AuthProvider } from "@/auth/AuthProvider"
// B5: fontes self-hosted (sem CDN do Google) — pesos do protótipo (Oswald 200–500 display,
// Outfit 300–600 corpo). Mantêm os nomes de família "Oswald"/"Outfit" que o tailwind.config usa.
// Removem a dependência de fonts.googleapis/gstatic em runtime → a CSP cai p/ font-src 'self'.
import "@fontsource/oswald/200.css"
import "@fontsource/oswald/300.css"
import "@fontsource/oswald/400.css"
import "@fontsource/oswald/500.css"
import "@fontsource/outfit/300.css"
import "@fontsource/outfit/400.css"
import "@fontsource/outfit/500.css"
import "@fontsource/outfit/600.css"
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
