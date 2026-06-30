import { LogOut, Settings } from "lucide-react"
import { NavLink, Outlet, useLocation } from "react-router-dom"

import { useAuth } from "@/auth/AuthProvider"
import { Wordmark } from "@/components/brand/Wordmark"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { AssistenteChat } from "@/features/assistente/AssistenteChat"

export function AppShell() {
  const { user, signOut } = useAuth()
  // Telas "painel" usam largura cheia (Comercial e o Orçamento do projeto); demais rotas seguem
  // estreitas (mobile-first). O header permanece max-w-3xl (a navbar não "salta" ao trocar de aba).
  const { pathname } = useLocation()
  const wide =
    pathname.startsWith("/comercial") ||
    pathname.startsWith("/orcamentos") ||
    pathname.endsWith("/orcamento")
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur-xl">
        <div className="mx-auto flex h-14 w-full max-w-3xl items-center justify-between px-5">
          <div className="flex items-center gap-5">
            <Wordmark className="text-lg" />
            <nav className="flex items-center gap-1">
              {/* Ordem = fluxo cronológico da operação: prospecção → projeto → orçamento → execução. */}
              <NavItem to="/comercial" label="Comercial" />
              <NavItem to="/projetos" label="Projetos" />
              <NavItem to="/orcamentos" label="Orçamentos" />
              <NavItem to="/" label="Obras" />
              <NavItem to="/biblioteca" label="Biblioteca" />
            </nav>
          </div>
          <div className="flex items-center gap-3">
            {user?.email && (
              <span className="hidden max-w-[10rem] truncate text-xs text-muted-foreground sm:block">
                {user.email}
              </span>
            )}
            <NavLink
              to="/configuracoes"
              aria-label="Configurações"
              title="Configurações"
              className={({ isActive }) =>
                cn(
                  "inline-flex size-9 items-center justify-center rounded-lg transition-colors hover:bg-accent hover:text-foreground",
                  isActive ? "text-primary" : "text-muted-foreground",
                )
              }
            >
              <Settings className="size-4" />
            </NavLink>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => void signOut()}
              aria-label="Sair"
              title="Sair"
            >
              <LogOut className="size-4" />
            </Button>
          </div>
        </div>
      </header>
      <main
        className={cn(
          "mx-auto w-full pb-24 pt-6",
          wide ? "max-w-[1600px] px-5 lg:px-8" : "max-w-3xl px-5",
        )}
      >
        <Outlet />
      </main>
      <AssistenteChat />
    </div>
  )
}

function NavItem({ to, label }: { to: string; label: string }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        cn(
          "rounded-lg px-2.5 py-1.5 text-sm font-medium transition-colors",
          isActive ? "text-foreground" : "text-muted-foreground hover:text-foreground",
        )
      }
    >
      {label}
    </NavLink>
  )
}
