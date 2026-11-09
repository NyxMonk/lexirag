import { FileText, Search, Upload } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Page, PageHeader } from "@/components/layout/Page";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DocumentFilters, type StatusFilter } from "@/features/documents/DocumentFilters";
import { DocumentTable } from "@/features/documents/DocumentTable";
import { UploadDialog } from "@/features/documents/UploadDialog";
import { useDocuments, useWorkspaces } from "@/hooks/queries";
import { useDebounced } from "@/hooks/useDebounced";

export function DocumentsPage() {
  const workspaces = useWorkspaces();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [workspaceId, setWorkspaceId] = useState("all");
  const [uploadOpen, setUploadOpen] = useState(false);
  const debouncedSearch = useDebounced(search);

  const documents = useDocuments({
    workspace_id: workspaceId === "all" ? undefined : workspaceId,
    search: debouncedSearch.trim() || undefined,
    status: status === "all" ? undefined : status,
    limit: 500,
  });
  const filtered = Boolean(debouncedSearch.trim()) || status !== "all" || workspaceId !== "all";
  const noWorkspaces = workspaces.data?.length === 0;

  return (
    <Page>
      <PageHeader
        eyebrow="Library"
        title="Documents"
        description="Every document across your workspaces."
        actions={
          <Button onClick={() => setUploadOpen(true)} disabled={noWorkspaces}>
            <Upload /> Upload
          </Button>
        }
      />

      <div className="mb-4 flex items-center gap-2">
        <DocumentFilters search={search} onSearchChange={setSearch} status={status} onStatusChange={setStatus} />
        <Select value={workspaceId} onValueChange={setWorkspaceId}>
          <SelectTrigger className="w-56" aria-label="Filter by workspace">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All workspaces</SelectItem>
            {workspaces.data?.map((w) => (
              <SelectItem key={w.id} value={w.id}>
                {w.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {documents.isLoading ? (
        <Skeleton className="h-72" />
      ) : documents.isError ? (
        <ErrorState error={documents.error} onRetry={() => documents.refetch()} />
      ) : documents.data!.length === 0 ? (
        filtered ? (
          <EmptyState compact icon={Search} title="No matching documents" description="Adjust the filters to see more." />
        ) : (
          <EmptyState
            icon={FileText}
            title="Your library is empty"
            description={noWorkspaces ? "Create a workspace, then upload PDF documents to it." : "Upload PDF documents to get started."}
          />
        )
      ) : (
        <DocumentTable documents={documents.data!} workspaces={workspaces.data ?? []} />
      )}

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
    </Page>
  );
}
