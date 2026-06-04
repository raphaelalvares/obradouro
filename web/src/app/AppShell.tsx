import { LogOut, Settings } from "lucide-react"
import { NavLink, Outlet } from "react-router-dom"

import { useAuth } from "@/auth/AuthProvider"
import { Wordmark } from "@/components/brand/Wordmark"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function AppShell() {
  const { user, signOut } = useAuth()
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur-xl">
        <div className="mx-auto flex h-14 w-full max-w-3xl items-center justify-between px-5">
          <div className="flex items-center gap-5">
            <Wordmark className="text-lg" />
            <nav className="flex items-center gap-1">
              <NavItem to="/" label="Obras" />
              <NavItem to="/projetos" label="Projetos" />
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
      <main className="mx-auto w-full max-w-3xl px-5 pb-24 pt-6">
        <Outlet />
      </main>
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
