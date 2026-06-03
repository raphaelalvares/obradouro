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
})
