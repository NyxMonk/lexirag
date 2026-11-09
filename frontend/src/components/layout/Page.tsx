import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Page({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mx-auto w-full max-w-[1180px] px-10 pb-16 pt-10", className)}>{children}</div>;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-9 flex items-end justify-between gap-6 border-b pb-7">
      <div className="min-w-0">
        {eyebrow && <div className="label-caps mb-3">{eyebrow}</div>}
        <h1 className="display truncate text-[34px] leading-[1.1]">{title}</h1>
        {description && <p className="mt-2.5 max-w-2xl text-[14.5px] text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}

export function SectionHeader({ title, action }: { title: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h2 className="text-[13px] font-semibold tracking-tight">{title}</h2>
      {action}
    </div>
  );
}
