import path from "node:path"

import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// Painel web do arquiteto. SPA pura — consome a API Python; Supabase só p/ auth no browser.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: { port: 5173 },
  build: {
    // Fontes NUNCA inline como data: — a CSP é font-src 'self' (B5). Subsets pequenos (ex.: Oswald
    // 'vietnamese' <4KB) seriam embutidos como data:woff2 pelo limite padrão e a CSP os bloquearia.
    // Imagens seguem o padrão do Vite (a CSP já libera img-src data:).
    assetsInlineLimit: (file) => (/\.(woff2?|ttf|otf|eot)$/i.test(file) ? false : undefined),
  },
})
