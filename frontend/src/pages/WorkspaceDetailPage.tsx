import { ChevronRight, FileText, MessageSquareText, MoreHorizontal, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Page, PageHeader, SectionHeader } from "@/components/layout/Page";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/misc";
import { DocumentFilters, type StatusFilter } from "@/features/documents/DocumentFilters";
import { DocumentTable } from "@/features/documents/DocumentTable";
import { UploadPanel } from "@/features/documents/UploadPanel";
import { useDeleteWorkspace, useDocuments, useWorkspace } from "@/hooks/queries";
import { useDebounced } from "@/hooks/useDebounced";
import { useToast } from "@/hooks/useToast";
import { formatDate, pluralize } from "@/lib/utils";
import { ApiError } from "@/services/api";

export function WorkspaceDetailPage() {
  const { workspaceId = "" } = useParams();
  const workspace = useWorkspace(workspaceId);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const debouncedSearch = useDebounced(search);
  const documents = useDocuments({
    workspace_id: workspaceId,
    search: debouncedSearch.trim() || undefined,
    status: status === "all" ? undefined : status,
  });
  const [confirmDelete, setConfirmDelete] = useState(false);
  const del = useDeleteWorkspace();
  const navigate = useNavigate();
  const { toast } = useToast();

  if (workspace.isError) {
    const notFound = workspace.error instanceof ApiError && workspace.error.status === 404;
    return (
      <Page>
        {notFound ? (
          <EmptyState
            icon={FileText}
            title="Workspace not found"
            description="It may have been deleted."
            action={
              <Button variant="outline" asChild>
                <Link to="/workspaces">Back to workspaces</Link>
              </Button>
            }
          />
        ) : (
          <ErrorState error={workspace.error} onRetry={() => workspace.refetch()} />
        )}
      </Page>
    );
  }

  const ws = workspace.data;
  const filtered = Boolean(debouncedSearch.trim()) || status !== "all";

  async function onDelete() {
    if (!ws) return;
    try {
      await del.mutateAsync(ws.id);
      toast({ title: "Workspace deleted", description: ws.name });
      navigate("/workspaces");
    } catch (err) {
      toast({ title: "Could not delete workspace", description: (err as Error).message, tone: "error" });
    }
  }

  return (
    <Page>
      <nav className="mb-5 flex items-center gap-1.5 text-[12.5px] text-muted-foreground" aria-label="Breadcrumb">
        <Link to="/workspaces" className="hover:text-foreground">
          Workspaces
        </Link>
        <ChevronRight className="h-3 w-3" />
        <span className="truncate text-foreground">{ws?.name ?? "…"}</span>
      </nav>

      {ws ? (
        <PageHeader
          title={ws.name}
          description={ws.description || undefined}
          actions={
            <>
              <Button variant="outline" asChild>
                <Link to={`/assistant?workspace=${ws.id}`}>
                  <MessageSquareText /> Ask
                </Link>
              </Button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="icon" className="h-9 w-9" aria-label="Workspace actions">
                    <MoreHorizontal />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem destructive onSelect={() => setConfirmDelete(true)}>
                    <Trash2 /> Delete workspace
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          }
        />
      ) : (
        <div className="mb-9 border-b pb-7">
          <Skeleton className="h-10 w-80" />
          <Skeleton className="mt-3 h-4 w-96" />
        </div>
      )}

      <div className="grid grid-cols-[1fr_320px] gap-8">
        <section className="min-w-0">
          <h2 className="mb-3 text-[13px] font-semibold tracking-tight">
            Documents
            {ws && <span className="ml-2 font-normal text-muted-foreground">{ws.document_count}</span>}
          </h2>
          <div className="mb-4">
            <DocumentFilters search={search} onSearchChange={setSearch} status={status} onStatusChange={setStatus} />
          </div>
          {documents.isLoading ? (
            <Skeleton className="h-64" />
          ) : documents.isError ? (
            <ErrorState error={documents.error} onRetry={() => documents.refetch()} />
          ) : documents.data!.length === 0 ? (
            filtered ? (
              <EmptyState compact icon={Search} title="No matching documents" description="Try a different name or status." />
            ) : (
              <EmptyState
                icon={FileText}
                title="No documents in this workspace"
                description="Drop PDF files into the upload area to add them."
              />
            )
          ) : (
            <DocumentTable documents={documents.data!} />
          )}
        </section>

        <aside className="space-y-8">
          <div>
            <SectionHeader title="Add documents" />
            {workspaceId && <UploadPanel workspaceId={workspaceId} />}
          </div>
          {ws && (
            <div>
              <SectionHeader title="Details" />
              <dl className="divide-y rounded-lg border bg-card text-[13px] shadow-subtle">
                {[
                  ["Documents", pluralize(ws.document_count, "document")],
                  ["Conversations", pluralize(ws.conversation_count, "conversation")],
                  ["Created", formatDate(ws.created_at)],
                  ["Last activity", formatDate(ws.updated_at)],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between px-4 py-2.5">
                    <dt className="text-muted-foreground">{k}</dt>
                    <dd className="tabular-nums">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </aside>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete workspace?"
        description={
          <>
            <span className="font-medium text-foreground">{ws?.name}</span> and{" "}
            {pluralize(ws?.document_count ?? 0, "document")} (including the stored files) will be permanently removed.
          </>
        }
        confirmLabel="Delete workspace"
        pending={del.isPending}
        onConfirm={onDelete}
      />
    </Page>
  );
}
