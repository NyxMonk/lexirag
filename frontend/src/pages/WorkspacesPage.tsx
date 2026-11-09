import { FolderClosed, FolderPlus, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Page, PageHeader } from "@/components/layout/Page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/misc";
import { CreateWorkspaceDialog } from "@/features/workspaces/CreateWorkspaceDialog";
import { WorkspaceCard } from "@/features/workspaces/WorkspaceCard";
import { useWorkspaces } from "@/hooks/queries";

export function WorkspacesPage() {
  const workspaces = useWorkspaces();
  const [filter, setFilter] = useState("");
  const [createOpen, setCreateOpen] = useState(false);

  const visible = useMemo(() => {
    const q = filter.trim().toLocaleLowerCase();
    return (workspaces.data ?? []).filter(
      (w) => !q || w.name.toLocaleLowerCase().includes(q) || w.description?.toLocaleLowerCase().includes(q),
    );
  }, [workspaces.data, filter]);

  return (
    <Page>
      <PageHeader
        eyebrow="Library"
        title="Workspaces"
        description="Each workspace holds the documents and conversations for one matter."
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <FolderPlus /> New workspace
          </Button>
        }
      />

      {(workspaces.data?.length ?? 0) > 0 && (
        <div className="relative mb-5 w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            aria-label="Filter workspaces"
            placeholder="Filter workspaces"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="pl-8"
          />
        </div>
      )}

      {workspaces.isLoading ? (
        <div className="grid grid-cols-3 gap-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-[148px]" />
          ))}
        </div>
      ) : workspaces.isError ? (
        <ErrorState error={workspaces.error} onRetry={() => workspaces.refetch()} />
      ) : workspaces.data!.length === 0 ? (
        <EmptyState
          icon={FolderClosed}
          title="No workspaces yet"
          description="Create a workspace to start collecting the documents for a matter."
          action={
            <Button onClick={() => setCreateOpen(true)}>
              <FolderPlus /> New workspace
            </Button>
          }
        />
      ) : visible.length === 0 ? (
        <EmptyState compact icon={Search} title="No matching workspaces" description={`Nothing matches “${filter}”.`} />
      ) : (
        <div className="grid grid-cols-3 gap-3">
          {visible.map((w) => (
            <WorkspaceCard key={w.id} workspace={w} />
          ))}
        </div>
      )}

      <CreateWorkspaceDialog open={createOpen} onOpenChange={setCreateOpen} />
    </Page>
  );
}
