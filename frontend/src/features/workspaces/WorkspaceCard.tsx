import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";

import { formatRelative, pluralize } from "@/lib/utils";
import type { Workspace } from "@/types/api";

export function WorkspaceCard({ workspace }: { workspace: Workspace }) {
  return (
    <Link
      to={`/workspaces/${workspace.id}`}
      className="group relative flex min-h-[148px] flex-col rounded-lg border bg-card p-5 shadow-subtle transition-[border-color,box-shadow,transform] duration-200 hover:-translate-y-px hover:border-foreground/20 hover:shadow-lifted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex items-start justify-between gap-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-md border bg-muted font-serif text-[15px]">
          {workspace.name.trim().charAt(0).toUpperCase()}
        </span>
        <ArrowUpRight className="h-4 w-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
      </div>
      <h3 className="mt-4 truncate text-[15px] font-medium">{workspace.name}</h3>
      <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-muted-foreground">
        {workspace.description || "No description"}
      </p>
      <div className="mt-auto flex items-center gap-3 pt-4 text-[12px] text-muted-foreground">
        <span>{pluralize(workspace.document_count, "document")}</span>
        <span className="h-0.5 w-0.5 rounded-full bg-muted-foreground/60" />
        <span>Updated {formatRelative(workspace.updated_at)}</span>
      </div>
    </Link>
  );
}
