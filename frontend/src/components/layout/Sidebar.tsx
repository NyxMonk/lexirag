import { FileText, FolderClosed, LayoutGrid, MessageSquareText, Settings } from "lucide-react";
import { NavLink } from "react-router-dom";

import { BrandLockup } from "@/components/brand/Brand";
import { useHealth, useWorkspaces } from "@/hooks/queries";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutGrid, end: true },
  { to: "/workspaces", label: "Workspaces", icon: FolderClosed },
  { to: "/documents", label: "Documents", icon: FileText },
  { to: "/assistant", label: "Assistant", icon: MessageSquareText },
];

function navClass({ isActive }: { isActive: boolean }) {
  return cn(
    "group flex h-8 items-center gap-2.5 rounded-md px-2.5 text-[13.5px] transition-colors",
    isActive
      ? "bg-accent font-medium text-foreground"
      : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
  );
}

export function Sidebar() {
  const workspaces = useWorkspaces();
  const health = useHealth();
  const recent = (workspaces.data ?? []).slice(0, 5);

  const connected = health.data?.status === "ok";
  const statusLabel = health.isLoading
    ? "Connecting…"
    : connected
      ? "Local server connected"
      : health.data
        ? "Database unavailable"
        : "Server unreachable";

  return (
    <aside className="flex h-full w-[248px] shrink-0 flex-col border-r bg-surface">
      <div className="flex h-14 items-center px-5">
        <NavLink to="/" aria-label="LexiRAG home" className="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <BrandLockup />
        </NavLink>
      </div>

      <nav className="flex flex-col gap-0.5 px-3 pt-3" aria-label="Primary">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={navClass}>
            <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="mt-7 px-5">
        <p className="label-caps">Workspaces</p>
      </div>
      <div className="mt-2 flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-3">
        {recent.length === 0 && !workspaces.isLoading && (
          <p className="px-2.5 py-1 text-[13px] text-muted-foreground/80">None yet</p>
        )}
        {recent.map((w) => (
          <NavLink key={w.id} to={`/workspaces/${w.id}`} className={navClass} title={w.name}>
            <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] border text-[9px] font-semibold uppercase text-muted-foreground">
              {w.name.trim().charAt(0)}
            </span>
            <span className="truncate">{w.name}</span>
          </NavLink>
        ))}
      </div>

      <div className="border-t px-3 py-3">
        <NavLink to="/settings" className={navClass}>
          <Settings className="h-4 w-4 shrink-0" strokeWidth={1.75} />
          Settings
        </NavLink>
        <div className="mt-2 flex items-center gap-2 px-2.5 text-[12px] text-muted-foreground" role="status">
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              health.isLoading ? "bg-muted-foreground/40" : connected ? "bg-emerald-600" : "bg-destructive",
            )}
            aria-hidden
          />
          {statusLabel}
        </div>
      </div>
    </aside>
  );
}
