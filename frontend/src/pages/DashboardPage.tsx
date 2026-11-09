import { ArrowRight, FileText, FolderPlus, MessageSquareText, Upload } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { Page, PageHeader, SectionHeader } from "@/components/layout/Page";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, Skeleton } from "@/components/ui/misc";
import { UploadDialog } from "@/features/documents/UploadDialog";
import { CreateWorkspaceDialog } from "@/features/workspaces/CreateWorkspaceDialog";
import { WorkspaceCard } from "@/features/workspaces/WorkspaceCard";
import { useConversations, useDocuments, useWorkspaces } from "@/hooks/queries";
import { LANGUAGES } from "@/lib/languages";
import { formatBytes, formatRelative } from "@/lib/utils";

function greeting(date = new Date()) {
  const h = date.getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

function QuickAction({
  icon: Icon,
  title,
  description,
  onClick,
  to,
}: {
  icon: typeof FolderPlus;
  title: string;
  description: string;
  onClick?: () => void;
  to?: string;
}) {
  const inner = (
    <>
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border bg-background transition-colors group-hover:border-foreground/25">
        <Icon className="h-4 w-4" strokeWidth={1.7} />
      </span>
      <span className="min-w-0 text-left">
        <span className="block text-[14px] font-medium">{title}</span>
        <span className="block truncate text-[12.5px] text-muted-foreground">{description}</span>
      </span>
      <ArrowRight className="ml-auto h-4 w-4 shrink-0 -translate-x-1 text-muted-foreground opacity-0 transition-all group-hover:translate-x-0 group-hover:opacity-100" />
    </>
  );
  const className =
    "group flex items-center gap-3.5 rounded-lg border bg-card px-4 py-3.5 shadow-subtle transition-[border-color,box-shadow] duration-200 hover:border-foreground/20 hover:shadow-lifted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
  return to ? (
    <Link to={to} className={className}>
      {inner}
    </Link>
  ) : (
    <button type="button" onClick={onClick} className={className}>
      {inner}
    </button>
  );
}

function Stat({ label, value, note }: { label: string; value: ReactNode; note?: string }) {
  return (
    <div className="px-5 py-4">
      <p className="label-caps">{label}</p>
      <p className="mt-2 font-serif text-[28px] leading-none tabular-nums">{value}</p>
      {note && <p className="mt-2 text-[12px] text-muted-foreground">{note}</p>}
    </div>
  );
}

export function DashboardPage() {
  const workspaces = useWorkspaces();
  const documents = useDocuments({ limit: 500 });
  const conversations = useConversations();
  const [createOpen, setCreateOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);

  const docs = documents.data ?? [];
  const totalBytes = docs.reduce((sum, d) => sum + d.file_size, 0);
  const indexed = docs.filter((d) => d.processing_status === "completed").length;
  const isNew = workspaces.data?.length === 0;

  return (
    <Page>
      <PageHeader
        eyebrow={new Intl.DateTimeFormat(undefined, { weekday: "long", day: "numeric", month: "long" }).format(new Date())}
        title={greeting()}
        description="Your legal document library, organised by workspace."
        actions={
          <>
            <Button variant="outline" onClick={() => setUploadOpen(true)} disabled={isNew}>
              <Upload /> Upload
            </Button>
            <Button onClick={() => setCreateOpen(true)}>
              <FolderPlus /> New workspace
            </Button>
          </>
        }
      />

      {workspaces.isError && <ErrorState error={workspaces.error} onRetry={() => workspaces.refetch()} className="mb-8" />}

      {isNew ? (
        <Card className="mb-10 overflow-hidden">
          <div className="grid grid-cols-[1.1fr_1fr]">
            <div className="p-9">
              <p className="label-caps">Getting started</p>
              <h2 className="display mt-3 text-[28px] leading-tight">Understand law. Across languages.</h2>
              <p className="mt-3 max-w-md text-[14px] leading-relaxed text-muted-foreground">
                Create a workspace for a matter, add its documents, and ask questions in one language about
                documents written in another. Every answer cites the pages it relies on.
              </p>
              <ol className="mt-7 space-y-3 text-[13.5px]">
                {["Create a workspace", "Upload PDF documents", "Ask questions in your language"].map((step, i) => (
                  <li key={step} className="flex items-center gap-3">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full border text-[11px] font-semibold tabular-nums">
                      {i + 1}
                    </span>
                    <span>{step}</span>
                  </li>
                ))}
              </ol>
              <Button className="mt-8" onClick={() => setCreateOpen(true)}>
                <FolderPlus /> Create your first workspace
              </Button>
            </div>
            <div className="flex flex-col justify-center gap-2.5 border-l bg-muted/40 p-9">
              {LANGUAGES.map((l) => (
                <div key={l.code} className="flex items-baseline justify-between border-b border-dashed pb-2.5 last:border-0">
                  <span className="font-serif text-[22px] leading-none">{l.nativeName}</span>
                  <span className="label-caps">{l.script}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      ) : (
        <>
          <div className="mb-10 grid grid-cols-3 gap-3">
            <QuickAction icon={FolderPlus} title="New workspace" description="Organise a matter or client" onClick={() => setCreateOpen(true)} />
            <QuickAction icon={Upload} title="Upload documents" description="Add PDFs to a workspace" onClick={() => setUploadOpen(true)} />
            <QuickAction icon={MessageSquareText} title="Open assistant" description="Cross-language questions" to="/assistant" />
          </div>

          <Card className="mb-10 grid grid-cols-4 divide-x">
            <Stat label="Workspaces" value={workspaces.data?.length ?? "—"} />
            <Stat label="Documents" value={documents.data ? docs.length : "—"} />
            <Stat label="Stored" value={documents.data ? formatBytes(totalBytes) : "—"} />
            <Stat
              label="Indexed"
              value={documents.data ? `${indexed} / ${docs.length}` : "—"}
              note="Searchable by the assistant"
            />
          </Card>
        </>
      )}

      <div className="grid grid-cols-[1.6fr_1fr] gap-8">
        <section>
          <SectionHeader
            title="Recent documents"
            action={
              docs.length > 0 && (
                <Link to="/documents" className="text-[12.5px] text-muted-foreground hover:text-foreground">
                  View all
                </Link>
              )
            }
          />
          {documents.isLoading ? (
            <Skeleton className="h-56" />
          ) : documents.isError ? (
            <ErrorState error={documents.error} onRetry={() => documents.refetch()} />
          ) : docs.length === 0 ? (
            <EmptyState
              compact
              icon={FileText}
              title="No documents yet"
              description="Uploaded PDFs will appear here."
            />
          ) : (
            <Card className="divide-y">
              {docs.slice(0, 6).map((d) => (
                <Link
                  key={d.id}
                  to={`/documents/${d.id}`}
                  className="flex items-center gap-3 px-4 py-3 text-[13.5px] transition-colors first:rounded-t-lg last:rounded-b-lg hover:bg-accent/50"
                >
                  <FileText className="h-4 w-4 shrink-0 text-muted-foreground" strokeWidth={1.6} />
                  <span className="min-w-0 flex-1 truncate font-medium">{d.original_filename}</span>
                  <StatusBadge status={d.processing_status} progress={d.processing_progress} />
                  <span className="w-20 shrink-0 text-right text-[12px] text-muted-foreground">
                    {formatRelative(d.created_at)}
                  </span>
                </Link>
              ))}
            </Card>
          )}
        </section>

        <section>
          <SectionHeader title="Recent conversations" />
          {conversations.isLoading ? (
            <Skeleton className="h-56" />
          ) : conversations.isError ? (
            <ErrorState error={conversations.error} onRetry={() => conversations.refetch()} />
          ) : (conversations.data ?? []).length === 0 ? (
            <EmptyState
              compact
              icon={MessageSquareText}
              title="No conversations yet"
              description="Questions you ask in the assistant are saved here."
            />
          ) : (
            <Card className="divide-y">
              {conversations.data!.slice(0, 6).map((c) => (
                <Link
                  key={c.id}
                  to={`/assistant?workspace=${c.workspace_id}&conversation=${c.id}`}
                  className="flex items-center justify-between gap-3 px-4 py-3 text-[13.5px] transition-colors first:rounded-t-lg last:rounded-b-lg hover:bg-accent/50"
                >
                  <span className="truncate font-medium">{c.title}</span>
                  <span className="shrink-0 text-[12px] text-muted-foreground">{formatRelative(c.updated_at)}</span>
                </Link>
              ))}
            </Card>
          )}
        </section>
      </div>

      {!isNew && (workspaces.data?.length ?? 0) > 0 && (
        <section className="mt-12">
          <SectionHeader
            title="Workspaces"
            action={
              <Link to="/workspaces" className="text-[12.5px] text-muted-foreground hover:text-foreground">
                View all
              </Link>
            }
          />
          <div className="grid grid-cols-3 gap-3">
            {workspaces.data!.slice(0, 6).map((w) => (
              <WorkspaceCard key={w.id} workspace={w} />
            ))}
          </div>
        </section>
      )}

      <CreateWorkspaceDialog open={createOpen} onOpenChange={setCreateOpen} />
      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
    </Page>
  );
}
