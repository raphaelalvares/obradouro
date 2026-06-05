import * as DialogPrimitive from "@radix-ui/react-dialog"
import { X } from "lucide-react"
import {
  forwardRef,
  type ComponentPropsWithoutRef,
  type ElementRef,
  type HTMLAttributes,
} from "react"

import { cn } from "@/lib/utils"

export const Dialog = DialogPrimitive.Root
export const DialogTrigger = DialogPrimitive.Trigger
export const DialogClose = DialogPrimitive.Close

const DialogOverlay = forwardRef<
  ElementRef<typeof DialogPrimitive.Overlay>,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-50 bg-black/70 backdrop-blur-sm",
      "data-[state=open]:animate-fade-in",
      className,
    )}
    {...props}
  />
))
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName

export const DialogContent = forwardRef<
  ElementRef<typeof DialogPrimitive.Content>,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <DialogPrimitive.Portal>
    <DialogOverlay />
    {/*
      CENTRALIZAÇÃO (ver CLAUDE.md › "Dialogs / modais"). Wrapper flex centra sem `transform`
      (o `fade-up` anima translateY e clobbaria um `-translate-1/2`). O segredo do alinhamento no
      DESKTOP: compensar o GAP do scroll-lock do Radix — ao abrir, ele põe `padding-right` no <body>
      (largura da scrollbar) e expõe `--removed-body-scroll-bar-size`; o modal é `fixed` (viewport),
      então sem essa compensação ele centra numa largura diferente da do conteúdo da página → torto.
      Replicamos o mesmo padding-right aqui → o centro do modal bate com o centro do conteúdo.
      Mobile = sheet embaixo (items-end); em telas de toque o gap costuma ser 0 (scrollbar overlay).
    */}
    <div
      className={cn(
        "fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-4",
        "pr-[var(--removed-body-scroll-bar-size)]",
        "sm:pr-[calc(1rem_+_var(--removed-body-scroll-bar-size))]",
      )}
    >
      <DialogPrimitive.Content
        ref={ref}
        className={cn(
          "relative flex max-h-[90dvh] w-full flex-col gap-5 overflow-y-auto border border-border bg-popover p-6 shadow-2xl",
          // MOBILE: entrada só por opacidade (sem transform). O `translateY` do fade-up, em curso
          // enquanto o teclado do iOS sobe (autofocus), quebra o scroll-into-view e o sheet abre
          // torto na 1ª vez (ver CLAUDE.md › "Dialogs"). Sem transform, o iOS posiciona certo.
          "rounded-t-2xl data-[state=open]:animate-fade-in",
          // DESKTOP: sem teclado virtual → mantém o slide-up elegante.
          "sm:max-w-md sm:rounded-2xl sm:data-[state=open]:animate-fade-up",
          className,
        )}
        {...props}
      >
        {children}
        <DialogPrimitive.Close className="absolute right-4 top-4 rounded-lg p-1 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <X className="size-5" />
          <span className="sr-only">Fechar</span>
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </div>
  </DialogPrimitive.Portal>
))
DialogContent.displayName = DialogPrimitive.Content.displayName

export function DialogHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1.5", className)} {...props} />
}

export const DialogTitle = forwardRef<
  ElementRef<typeof DialogPrimitive.Title>,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn("font-word text-2xl", className)}
    {...props}
  />
))
DialogTitle.displayName = DialogPrimitive.Title.displayName

export const DialogDescription = forwardRef<
  ElementRef<typeof DialogPrimitive.Description>,
  ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props}
  />
))
DialogDescription.displayName = DialogPrimitive.Description.displayName
