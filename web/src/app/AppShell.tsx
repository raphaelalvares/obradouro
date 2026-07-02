import * as SheetPrimitive from "@radix-ui/react-dialog"
import { LogOut, Menu, Settings, Shield, X } from "lucide-react"
import { useState } from "react"
import { NavLink, Outlet, useLocation } from "react-router-dom"

import { useAuth } from "@/auth/AuthProvider"
import { Wordmark } from "@/components/brand/Wordmark"
import { Button } from "@/components/ui/button"
import { useIsAdmin, useNovosClientes } from "@/features/admin/adminApi"
import { cn } from "@/lib/utils"
import { AssistenteChat } from "@/features/assistente/AssistenteChat"

// Fonte única da navegação (desktop inline + drawer mobile). Ordem = fluxo cronológico da operação:
// prospecção → projeto → orçamento → execução.
const NAV = [
  { to: "/comercial", label: "Comercial" },
  { to: "/projetos", label: "Projetos" },
  { to: "/orcamentos", label: "Orçamentos" },
  { to: "/", label: "Obras", end: true },
  { to: "/biblioteca", label: "Biblioteca" },
]

export function AppShell() {
  const { user, signOut } = useAuth()
  const ehAdmin = useIsAdmin().data?.is_admin ?? false
  const novos = useNovosClientes(ehAdmin).data?.novos ?? 0
  // Telas "painel" usam largura cheia (Comercial, o Orçamento do projeto e o Admin — tabela densa +
  // KPIs); demais rotas seguem estreitas (mobile-first). O header permanece max-w-3xl (a navbar não
  // "salta" ao trocar de aba).
  const { pathname } = useLocation()
  const wide =
    pathname.startsWith("/comercial") ||
    pathname.startsWith("/orcamentos") ||
    pathname.startsWith("/admin") ||
    pathname.endsWith("/orcamento")
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur-xl">
        <div className="mx-auto flex h-14 w-full max-w-3xl items-center justify-between gap-3 px-5">
          <div className="flex min-w-0 items-center gap-5">
            {/* hambúrguer — só mobile (< sm); no desktop a nav é inline ao lado */}
            <MobileNav ehAdmin={ehAdmin} novos={novos} email={user?.email} onSignOut={signOut} />
            <Wordmark className="text-lg" />
            <nav className="hidden items-center gap-1 sm:flex">
              {NAV.map((n) => (
                <NavItem key={n.to} to={n.to} label={n.label} end={n.end} />
              ))}
            </nav>
          </div>
          {/* email + ícones: só desktop. No mobile tudo isso vive dentro do drawer. */}
          <div className="hidden items-center gap-3 sm:flex">
            {user?.email && (
              <span className="max-w-[10rem] truncate text-xs text-muted-foreground">
                {user.email}
              </span>
            )}
            {ehAdmin && (
              <NavLink
                to="/admin"
                aria-label="Admin"
                title={novos > 0 ? `${novos} novo(s) cadastro(s)` : "Admin da plataforma"}
                className={({ isActive }) =>
                  cn(
                    "relative inline-flex size-9 items-center justify-center rounded-lg transition-colors hover:bg-accent hover:text-foreground",
                    isActive ? "text-primary" : "text-muted-foreground",
                  )
                }
              >
                <Shield className="size-4" />
                {novos > 0 && (
                  <span className="absolute -right-0.5 -top-0.5 flex min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold leading-4 text-primary-foreground">
                    {novos > 9 ? "9+" : novos}
                  </span>
                )}
              </NavLink>
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

// Menu lateral do mobile: hambúrguer → drawer da esquerda (Radix Dialog primitivo, deslizando com
// `slide-in-left`). Só existe abaixo de `sm` (o botão é `sm:hidden`); no desktop a nav é inline.
function MobileNav({
  ehAdmin,
  novos,
  email,
  onSignOut,
}: {
  ehAdmin: boolean
  novos: number
  email?: string | null
  onSignOut: () => void | Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const fechar = () => setOpen(false)
  return (
    <SheetPrimitive.Root open={open} onOpenChange={setOpen}>
      <SheetPrimitive.Trigger
        aria-label="Abrir menu"
        className="relative inline-flex size-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground sm:hidden"
      >
        <Menu className="size-5" />
        {/* badge de novos cadastros migra p/ o hambúrguer no mobile (o admin não perde o aviso) */}
        {ehAdmin && novos > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold leading-4 text-primary-foreground">
            {novos > 9 ? "9+" : novos}
          </span>
        )}
      </SheetPrimitive.Trigger>
      <SheetPrimitive.Portal>
        <SheetPrimitive.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm data-[state=open]:animate-fade-in sm:hidden" />
        <SheetPrimitive.Content
          aria-describedby={undefined}
          className="fixed inset-y-0 left-0 z-50 flex w-[82vw] max-w-xs flex-col border-r border-border bg-popover p-5 shadow-2xl data-[state=open]:animate-slide-in-left sm:hidden"
        >
          <SheetPrimitive.Title className="sr-only">Menu de navegação</SheetPrimitive.Title>
          <div className="mb-5 flex items-center justify-between">
            <Wordmark className="text-base" />
            <SheetPrimitive.Close
              aria-label="Fechar menu"
              className="inline-flex size-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <X className="size-5" />
            </SheetPrimitive.Close>
          </div>

          <nav className="flex flex-col gap-1">
            {NAV.map((n) => (
              <DrawerLink key={n.to} to={n.to} label={n.label} end={n.end} onClick={fechar} />
            ))}
          </nav>

          <div className="my-3 border-t border-border" />

          {ehAdmin && (
            <DrawerLink to="/admin" label="Admin" icon={Shield} badge={novos} onClick={fechar} />
          )}
          <DrawerLink to="/configuracoes" label="Configurações" icon={Settings} onClick={fechar} />

          <div className="mt-auto flex flex-col gap-3 pt-6">
            {email && <span className="truncate text-xs text-muted-foreground">{email}</span>}
            <Button
              variant="outline"
              onClick={() => {
                fechar()
                void onSignOut()
              }}
            >
              <LogOut className="size-4" /> Sair
            </Button>
          </div>
        </SheetPrimitive.Content>
      </SheetPrimitive.Portal>
    </SheetPrimitive.Root>
  )
}

// Link do drawer: alvo grande (mobile), com ícone/badge opcionais.
function DrawerLink({
  to,
  label,
  end,
  icon: Icon,
  badge,
  onClick,
}: {
  to: string
  label: string
  end?: boolean
  icon?: React.ComponentType<{ className?: string }>
  badge?: number
  onClick: () => void
}) {
  return (
    <NavLink
      to={to}
      end={end}
      onClick={onClick}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-lg px-3 py-2.5 text-base font-medium transition-colors",
          isActive ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground",
        )
      }
    >
      {Icon && <Icon className="size-4 shrink-0" />}
      <span className="flex-1">{label}</span>
      {badge != null && badge > 0 && (
        <span className="flex min-w-5 items-center justify-center rounded-full bg-primary px-1.5 text-[11px] font-semibold leading-5 text-primary-foreground">
          {badge > 9 ? "9+" : badge}
        </span>
      )}
    </NavLink>
  )
}

function NavItem({ to, label, end }: { to: string; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end ?? to === "/"}
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
