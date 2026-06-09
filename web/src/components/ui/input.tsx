import { forwardRef, type InputHTMLAttributes } from "react"

import { cn } from "@/lib/utils"

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        ref={ref}
        className={cn(
          // text-base (16px) no mobile evita o auto-zoom do iOS ao focar; text-sm no desktop (sm+).
          // min-w-0: deixa o input encolher dentro de grid/flex — sem isso o type="date" do iOS
          // mantém a largura nativa ("9 de jun. de 2026") e ESTOURA a célula (some no canto + zoom).
          "flex h-11 w-full min-w-0 rounded-xl border border-input bg-card px-4 py-2 text-base sm:text-sm",
          "placeholder:text-muted-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          "disabled:cursor-not-allowed disabled:opacity-50",
          "aria-[invalid=true]:border-destructive aria-[invalid=true]:ring-destructive",
          className,
        )}
        {...props}
      />
    )
  },
)
Input.displayName = "Input"
