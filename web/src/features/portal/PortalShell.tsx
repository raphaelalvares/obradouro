import { LogOut } from "lucide-react"
import { Link, Outlet } from "react-router-dom"

import { useAuth } from "@/auth/AuthProvider"
import { Wordmark } from "@/components/brand/Wordmark"
import { Button } from "@/components/ui/button"

/** Shell ENXUTA do portal do cliente: sem o nav do arquiteto. Mobile-first; o cliente vê só o que é
 * dele (proposta/revisões do projeto + acompanhamento da obra). Quem decide PortalShell × AppShell é
 * o RoleShell (por papel do contexto). */
export function PortalShell() {
  const { user, signOut } = useAuth()
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur-xl">
        <div className="mx-auto flex h-14 w-full max-w-3xl items-center justify-between px-5">
          <div className="flex items-center gap-3">
            <Link to="/" aria-label="Início">
              <Wordmark className="text-lg" />
            </Link>
            <span className="text-[10px] uppercase tracking-[0.3em] text-primary">Portal</span>
          </div>
          <div className="flex items-center gap-3">
            {user?.email && (
              <span className="hidden max-w-[10rem] truncate text-xs text-muted-foreground sm:block">
                {user.email}
              </span>
            )}
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
