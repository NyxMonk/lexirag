import { Eye, FileText, MoreHorizontal, Play, RotateCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useDeleteDocument, useProcessDocument } from "@/hooks/queries";
import { usePreferences } from "@/hooks/usePreferences";
import { useToast } from "@/hooks/useToast";
import { formatBytes, formatDate } from "@/lib/utils";
import type { DocumentRecord, Workspace } from "@/types/api";

export function DocumentTable({
  documents,
  workspaces,
}: {
  documents: DocumentRecord[];
  /** When provided, a workspace column is shown. */
  workspaces?: Workspace[];
}) {
  const [pendingDelete, setPendingDelete] = useState<DocumentRecord | null>(null);
  const del = useDeleteDocument();
  const process = useProcessDocument();
  const { preferences } = usePreferences();
  const { toast } = useToast();
  const navigate = useNavigate();
  const workspaceName = (id: string) => workspaces?.find((w) => w.id === id)?.name ?? "—";

  async function remove(doc: DocumentRecord) {
    try {
      await del.mutateAsync(doc.id);
      toast({ title: "Document deleted", description: doc.original_filename });
      setPendingDelete(null);
    } catch (err) {
      toast({ title: "Could not delete document", description: (err as Error).message, tone: "error" });
    }
  }

  async function runProcessing(doc: DocumentRecord, mode: "process" | "reprocess" | "retry") {
    try {
      await process.mutateAsync({ id: doc.id, mode });
      toast({ title: mode === "retry" ? "Processing retried" : "Processing queued", description: doc.original_filename });
    } catch (err) {
      toast({ title: "Could not start processing", description: (err as Error).message, tone: "error" });
    }
  }

  function requestDelete(doc: DocumentRecord) {
    if (preferences.confirmBeforeDelete) setPendingDelete(doc);
    else void remove(doc);
  }

  return (
    <>
      <div className="overflow-hidden rounded-lg border bg-card shadow-subtle">
        <table className="w-full text-[13.5px]">
          <thead>
            <tr className="border-b bg-muted/40 text-left">
              <th className="label-caps px-4 py-2.5 font-medium">Name</th>
              {workspaces && <th className="label-caps px-4 py-2.5 font-medium">Workspace</th>}
              <th className="label-caps w-[110px] px-4 py-2.5 text-right font-medium">Size</th>
              <th className="label-caps w-[190px] px-4 py-2.5 font-medium">Status</th>
              <th className="label-caps w-[130px] px-4 py-2.5 font-medium">Added</th>
              <th className="w-12 px-2" aria-label="Actions" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {documents.map((doc) => (
              <tr
                key={doc.id}
                className="group cursor-pointer transition-colors hover:bg-accent/40"
                onClick={() => navigate(`/documents/${doc.id}`)}
              >
                <td className="max-w-0 px-4 py-3">
                  <div className="flex items-center gap-3">
                    <FileText className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.6} />
                    <Link
                      to={`/documents/${doc.id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="truncate font-medium hover:underline hover:underline-offset-4"
                      title={doc.original_filename}
                    >
                      {doc.original_filename}
                    </Link>
                  </div>
                </td>
                {workspaces && (
                  <td className="max-w-[200px] truncate px-4 py-3 text-muted-foreground">
                    {workspaceName(doc.workspace_id)}
                  </td>
                )}
                <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">{formatBytes(doc.file_size)}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={doc.processing_status} progress={doc.processing_progress} />
                  {doc.processing_status === "failed" && doc.processing_error && (
                    <p className="mt-1 max-w-[220px] truncate text-[11.5px] text-destructive" title={doc.processing_error}>
                      {doc.processing_error}
                    </p>
                  )}
                </td>
                <td className="px-4 py-3 tabular-nums text-muted-foreground">{formatDate(doc.created_at)}</td>
                <td className="px-2 py-3" onClick={(e) => e.stopPropagation()}>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Actions for ${doc.original_filename}`}
                        className="opacity-60 group-hover:opacity-100 data-[state=open]:opacity-100"
                      >
                        <MoreHorizontal />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onSelect={() => navigate(`/documents/${doc.id}`)}>
                        <Eye /> Open
                      </DropdownMenuItem>
                      {doc.processing_status === "uploaded" && (
                        <DropdownMenuItem onSelect={() => runProcessing(doc, "process")}>
                          <Play /> Process
                        </DropdownMenuItem>
                      )}
                      {doc.processing_status === "failed" && (
                        <DropdownMenuItem onSelect={() => runProcessing(doc, "retry")}>
                          <RotateCw /> Retry processing
                        </DropdownMenuItem>
                      )}
                      {doc.processing_status === "completed" && (
                        <DropdownMenuItem onSelect={() => runProcessing(doc, "reprocess")}>
                          <RotateCw /> Re-index
                        </DropdownMenuItem>
                      )}
                      <DropdownMenuSeparator />
                      <DropdownMenuItem destructive onSelect={() => requestDelete(doc)}>
                        <Trash2 /> Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title="Delete document?"
        description={
          <>
            <span className="font-medium text-foreground">{pendingDelete?.original_filename}</span> and its stored file
            will be permanently removed.
          </>
        }
        pending={del.isPending}
        onConfirm={() => pendingDelete && remove(pendingDelete)}
      />
    </>
  );
}
