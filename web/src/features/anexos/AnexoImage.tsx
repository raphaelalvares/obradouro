import { useQuery } from "@tanstack/react-query"
import { ImageOff, Loader2 } from "lucide-react"
import { useEffect, useState } from "react"

import { api } from "@/lib/api"
import { cn } from "@/lib/utils"

/** Busca os bytes (full|thumb) por fetch autenticado e devolve um object URL (revogado no unmount).
 * Cacheado no React Query pela `path`, então o mesmo thumb não é rebaixado a cada render. */
function useBlobUrl(path: string, enabled: boolean) {
  const q = useQuery({
    queryKey: ["blob", path],
    queryFn: () => api.getBlob(path),
    enabled,
    staleTime: 5 * 60 * 1000,
    gcTime: 5 * 60 * 1000,
  })
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!q.data) return
    const u = URL.createObjectURL(q.data)
    setUrl(u)
    return () => URL.revokeObjectURL(u)
  }, [q.data])
  return { url, isLoading: q.isLoading, isError: q.isError }
}

export function AnexoImage({
  path,
  alt,
  className,
  fit = "cover",
  enabled = true,
}: {
  path: string
  alt: string
  className?: string
  fit?: "cover" | "contain"
  enabled?: boolean
}) {
  const { url, isLoading, isError } = useBlobUrl(path, enabled)

  if (isLoading || (!url && !isError)) {
    return (
      <div className={cn("flex items-center justify-center bg-accent/40 text-muted-foreground", className)}>
        <Loader2 className="size-5 animate-spin" />
      </div>
    )
  }
  if (isError || !url) {
    return (
      <div className={cn("flex items-center justify-center bg-accent/40 text-muted-foreground", className)}>
        <ImageOff className="size-5" />
      </div>
    )
  }
  return (
    <img
      src={url}
      alt={alt}
      loading="lazy"
      className={cn(fit === "cover" ? "object-cover" : "object-contain", className)}
    />
  )
}
