import { forwardRef, type TextareaHTMLAttributes } from "react"

import { cn } from "@/lib/utils"

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        className={cn(
          // text-base (16px) no mobile evita o auto-zoom do iOS ao focar; text-sm no desktop (sm+)
          "flex min-h-[80px] w-full rounded-xl border border-input bg-card px-4 py-3 text-base sm:text-sm",
          "placeholder:text-muted-foreground",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          "disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      />
    )
  },
)
Textarea.displayName = "Textarea"
