import { cn } from "@/lib/utils";

interface LoadingSkeletonProps {
  className?: string;
  variant?: "text" | "card" | "avatar" | "button" | "line";
  width?: string | number;
  height?: string | number;
  count?: number;
}

export function LoadingSkeleton({
  className,
  variant = "line",
  width,
  height,
  count = 1,
}: LoadingSkeletonProps) {
  const style: React.CSSProperties = {};
  if (width) style.width = typeof width === "number" ? `${width}px` : width;
  if (height) style.height = typeof height === "number" ? `${height}px` : height;

  const baseClass = "animate-pulse bg-muted rounded";

  if (variant === "card") {
    return (
      <div className={cn("rounded-xl border border-border bg-card p-5 space-y-3", className)} style={style}>
        <div className="flex items-center gap-3">
          <div className="w-16 h-4 rounded bg-muted animate-pulse" />
          <div className="w-24 h-4 rounded bg-muted animate-pulse" />
        </div>
        <div className="w-full h-2 rounded-full bg-muted animate-pulse" />
        <div className="w-3/4 h-3 rounded bg-muted animate-pulse" />
      </div>
    );
  }

  if (variant === "avatar") {
    return (
      <div className={cn("flex items-center gap-3", className)}>
        <div className={cn("rounded-full bg-muted animate-pulse shrink-0", className)} style={{ ...style, width: style.width || 40, height: style.height || 40 }} />
        <div className="flex-1 space-y-2">
          <div className="w-1/2 h-3 rounded bg-muted animate-pulse" />
          <div className="w-1/3 h-2 rounded bg-muted animate-pulse" />
        </div>
      </div>
    );
  }

  if (variant === "button") {
    return (
      <div className={cn("h-10 rounded-lg bg-muted animate-pulse", className)} style={style} />
    );
  }

  if (variant === "text") {
    return (
      <>
        {[...Array(count)].map((_, i) => (
          <div key={i} className={cn("h-3 rounded bg-muted animate-pulse", className)} style={style} />
        ))}
      </>
    );
  }

  // Default: line variant
  return (
    <>
      {[...Array(count)].map((_, i) => (
        <div key={i} className={cn(baseClass, className)} style={style} />
      ))}
    </>
  );
}

export function TaskListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {[...Array(count)].map((_, i) => (
        <LoadingSkeleton key={i} variant="card" />
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      <div className="hidden md:grid bg-muted/50 px-4 py-2.5 gap-3"
        style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
        {[...Array(cols)].map((_, i) => (
          <LoadingSkeleton key={i} variant="text" count={1} className="h-3" />
        ))}
      </div>
      {[...Array(rows)].map((_, i) => (
        <div key={i} className="border-t border-border px-4 py-3 grid gap-3" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}>
          {[...Array(cols)].map((_, j) => (
            <LoadingSkeleton key={j} variant="text" count={1} className="h-3" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function FormSkeleton({ fields = 4 }: { fields?: number }) {
  return (
    <div className="space-y-4">
      {[...Array(fields)].map((_, i) => (
        <div key={i} className="space-y-1.5">
          <LoadingSkeleton variant="text" count={1} className="h-3 w-24" />
          <LoadingSkeleton className="h-10 w-full" />
        </div>
      ))}
      <LoadingSkeleton className="h-10 w-32" />
    </div>
  );
}
