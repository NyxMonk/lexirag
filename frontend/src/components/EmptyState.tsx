import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
  compact = false,
}: {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-dashed text-center",
        compact ? "px-6 py-8" : "px-8 py-16",
        className,
      )}
    >
      <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border bg-surface shadow-subtle">
        <Icon className="h-[18px] w-[18px] text-muted-foreground" strokeWidth={1.6} />
      </div>
      <p className="text-[14.5px] font-medium">{title}</p>
      {description && <p className="mt-1.5 max-w-sm text-[13.5px] leading-relaxed text-muted-foreground">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
