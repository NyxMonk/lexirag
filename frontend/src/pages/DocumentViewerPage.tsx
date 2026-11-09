import { ArrowLeft, ChevronRight, Download, Loader2, Play, Quote, RotateCw, Sparkles, Trash2 } from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { LanguageSelect } from "@/components/LanguageSelect";
import { StatusBadge, statusHint } from "@/components/StatusBadge";
import { AssistantMessage } from "@/features/assistant/AnswerView";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import {
  useChunk,
  useDeleteDocument,
  useDocument,
  useProcessDocument,
  useSetLanguageOverride,
  useSummarizeDocument,
  useWorkspace,
} from "@/hooks/queries";
import { usePreferences } from "@/hooks/usePreferences";
import { useToast } from "@/hooks/useToast";
import { highlightPassages } from "@/lib/highlight";
import { languageLabel } from "@/lib/languages";
import { cn, formatBytes, formatDateTime } from "@/lib/utils";
import { api, ApiError } from "@/services/api";

// pdf.js is large; load it only when a document is opened.
const PdfViewer = lazy(() => import("@/features/documents/PdfViewer").then((m) => ({ default: m.PdfViewer })));

const LANGUAGE_STATUS: Record<string, string> = {
  detected: "",
  mixed: " (mixed-language document)",
  uncertain: " (uncertain)",
  unsupported: " (unsupported script)",
  empty: "",
};

export function DocumentViewerPage() {
  const { documentId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const doc = useDocument(documentId);
  const workspace = useWorkspace(doc.data?.workspace_id);
  const chunkId = params.get("chunk");
  const chunk = useChunk(documentId, chunkId);
  const location = useLocation();
  const quote = (location.state as { quote?: string | null } | null)?.quote ?? null;
  const [page, setPage] = useState(() => Number(params.get("page")) || 1);
  const [numPages, setNumPages] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const del = useDeleteDocument();
  const process = useProcessDocument();
  const override = useSetLanguageOverride();
  const summary = useSummarizeDocument();
  const [summaryLanguage, setSummaryLanguage] = useState<string | null>(null);
  const { preferences } = usePreferences();
  const summaryLang = summaryLanguage ?? (preferences.responseLanguage === "match" ? "en" : preferences.responseLanguage);
  const { toast } = useToast();
  const navigate = useNavigate();

  // Follow citation links that arrive while the viewer is already open.
  useEffect(() => {
    const target = Number(params.get("page"));
    if (target) setPage(target);
  }, [params]);

  if (doc.isError) {
    const notFound = doc.error instanceof ApiError && doc.error.status === 404;
    return (
      <div className="p-10">
        {notFound ? (
          <EmptyState
            icon={Quote}
            title="Document not found"
            description="It may have been deleted."
            action={
              <Button variant="outline" asChild>
                <Link to="/documents">Back to documents</Link>
              </Button>
            }
          />
        ) : (
          <ErrorState error={doc.error} onRetry={() => doc.refetch()} />
        )}
      </div>
    );
  }

  const d = doc.data;

  async function onDelete() {
    if (!d) return;
    try {
      await del.mutateAsync(d.id);
      toast({ title: "Document deleted", description: d.original_filename });
      navigate(`/workspaces/${d.workspace_id}`);
    } catch (err) {
      toast({ title: "Could not delete document", description: (err as Error).message, tone: "error" });
    }
  }

  async function runProcessing(mode: "process" | "reprocess" | "retry") {
    if (!d) return;
    try {
      await process.mutateAsync({ id: d.id, mode });
    } catch (err) {
      toast({ title: "Could not start processing", description: (err as Error).message, tone: "error" });
    }
  }

  async function changeLanguage(value: string) {
    if (!d) return;
    try {
      await override.mutateAsync({ id: d.id, language: value === "auto" ? null : value });
      toast({ title: value === "auto" ? "Using the detected language" : `Language set to ${languageLabel(value)}` });
    } catch (err) {
      toast({ title: "Could not change the language", description: (err as Error).message, tone: "error" });
    }
  }

  function changePage(next: number) {
    setPage(next);
    const updated = new URLSearchParams(params);
    updated.set("page", String(next));
    setParams(updated, { replace: true });
  }

  const cited = chunk.data;
  const citedHere = cited && page >= cited.page_start && page <= cited.page_end;

  return (
    <div className="flex h-full flex-col">
      <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b bg-surface px-6">
        <nav className="flex min-w-0 items-center gap-1.5 text-[13px] text-muted-foreground" aria-label="Breadcrumb">
          <Link to="/workspaces" className="hover:text-foreground">
            Workspaces
          </Link>
          <ChevronRight className="h-3 w-3 shrink-0" />
          {workspace.data ? (
            <Link to={`/workspaces/${workspace.data.id}`} className="truncate hover:text-foreground">
              {workspace.data.name}
            </Link>
          ) : (
            <span>…</span>
          )}
          <ChevronRight className="h-3 w-3 shrink-0" />
          <span className="truncate font-medium text-foreground">{d?.original_filename ?? "…"}</span>
        </nav>
        {d && (
          <div className="flex shrink-0 items-center gap-2">
            {chunkId && (
              <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
                <ArrowLeft /> Back to answer
              </Button>
            )}
            <Button variant="outline" size="sm" asChild>
              <a href={api.documentFileUrl(d.id)} target="_blank" rel="noreferrer">
                <Download /> Open original
              </a>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => (preferences.confirmBeforeDelete ? setConfirmDelete(true) : void onDelete())}
            >
              <Trash2 /> Delete
            </Button>
          </div>
        )}
      </header>

      <div className="flex min-h-0 flex-1">
        <section className="min-w-0 flex-1">
          {d ? (
            <Suspense fallback={<Skeleton className="m-8 h-[80vh]" />}>
              <PdfViewer
                url={api.documentFileUrl(d.id)}
                page={page}
                onPageChange={changePage}
                onLoaded={setNumPages}
                highlight={citedHere ? highlightPassages(quote, cited.content) : undefined}
              />
            </Suspense>
          ) : (
            <Skeleton className="m-8 h-[80vh]" />
          )}
        </section>

        <aside className="w-[340px] shrink-0 overflow-y-auto border-l bg-surface">
          <div className="border-b px-5 py-5">
            <p className="label-caps">Document</p>
            {d ? (
              <>
                <h1 className="display mt-2 break-words text-[20px] leading-snug">{d.original_filename}</h1>
                <div className="mt-3 flex items-center gap-2">
                  <StatusBadge status={d.processing_status} progress={d.processing_progress} />
                  {d.processing_status === "uploaded" && (
                    <Button size="sm" variant="outline" className="h-7" onClick={() => runProcessing("process")}>
                      <Play /> Process
                    </Button>
                  )}
                  {d.processing_status === "failed" && (
                    <Button size="sm" variant="outline" className="h-7" onClick={() => runProcessing("retry")}>
                      <RotateCw /> Retry
                    </Button>
                  )}
                </div>
                <p className="mt-3 text-[12.5px] leading-relaxed text-muted-foreground">{statusHint(d.processing_status)}</p>
                {d.processing_error && (
                  <p role="alert" className="mt-2 rounded-md border border-destructive/25 bg-destructive/[0.04] px-3 py-2 text-[12.5px]">
                    {d.processing_error}
                  </p>
                )}
              </>
            ) : (
              <Skeleton className="mt-2 h-6 w-48" />
            )}
          </div>

          {d && (
            <dl className="divide-y border-b text-[13px]">
              {[
                ["Pages", d.page_count ?? numPages ?? "—"],
                ["Indexed passages", d.chunk_count ?? "—"],
                ["File size", formatBytes(d.file_size)],
                [
                  "Detected language",
                  d.detected_language
                    ? `${languageLabel(d.detected_language)}${LANGUAGE_STATUS[d.language_status ?? "detected"] ?? ""}`
                    : d.processing_status === "completed"
                      ? `Not determined${LANGUAGE_STATUS[d.language_status ?? ""] ?? ""}`
                      : "After processing",
                ],
                ["Uploaded", formatDateTime(d.created_at)],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 px-5 py-2.5">
                  <dt className="shrink-0 text-muted-foreground">{k}</dt>
                  <dd className="text-right tabular-nums">{v}</dd>
                </div>
              ))}
              <div className="flex items-center justify-between gap-4 px-5 py-2.5">
                <dt className="text-muted-foreground">Language</dt>
                <dd>
                  <LanguageSelect
                    ariaLabel="Document language"
                    className="h-8 w-44"
                    value={d.language_override ?? "auto"}
                    onValueChange={changeLanguage}
                    extraOption={{ value: "auto", label: "Use detected" }}
                  />
                </dd>
              </div>
            </dl>
          )}

          {d?.processing_status === "completed" && (
            <div className="border-b px-5 py-5">
              <p className="label-caps">Summary</p>
              <div className="mt-3 flex items-center gap-2">
                <LanguageSelect
                  ariaLabel="Summary language"
                  className="h-8 flex-1"
                  value={summaryLang}
                  onValueChange={setSummaryLanguage}
                />
                <Button
                  size="sm"
                  onClick={() => summary.mutate({ id: d.id, language: summaryLang })}
                  disabled={summary.isPending}
                >
                  {summary.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
                  {summary.data ? "Regenerate" : "Summarise"}
                </Button>
              </div>
              {summary.isPending && (
                <p className="mt-3 text-[12.5px] text-muted-foreground" role="status">
                  Reading the indexed passages and drafting a cited summary…
                </p>
              )}
              {summary.isError && (
                <p role="alert" className="mt-3 rounded-md border border-destructive/25 bg-destructive/[0.04] px-3 py-2 text-[12.5px]">
                  {summary.error.message}
                </p>
              )}
              {summary.data && !summary.isPending && (
                <div className="mt-4 text-[13.5px] [&_p]:text-[13.5px]">
                  <AssistantMessage
                    message={{
                      id: "summary",
                      conversation_id: "",
                      role: "assistant",
                      content: summary.data.answer,
                      language: summary.data.language,
                      citations: summary.data.citations,
                      evidence_sufficient: summary.data.evidence_sufficient,
                      details: {
                        answer_source: summary.data.answer_source,
                        warnings: summary.data.warnings,
                        generation: summary.data.generation,
                      },
                      created_at: "",
                    }}
                  />
                </div>
              )}
            </div>
          )}

          {preferences.showCitationsPanel && (
            <div className="px-5 py-5">
              <p className="label-caps">Cited passage</p>
              {chunkId && chunk.isLoading && <Skeleton className="mt-3 h-28" />}
              {chunkId && chunk.isError && <ErrorState error={chunk.error} className="mt-3" />}
              {cited ? (
                <div className="mt-3 rounded-lg border bg-card p-4 shadow-subtle">
                  <p className="text-[12px] text-muted-foreground">
                    {cited.page_start === cited.page_end ? `Page ${cited.page_start}` : `Pages ${cited.page_start}–${cited.page_end}`}
                    {cited.section_title && ` · ${cited.section_title}`}
                  </p>
                  {quote && (
                    <p lang={cited.language ?? undefined} className="mt-2 border-l-2 border-amber-400 pl-3 font-serif text-[14px] leading-relaxed">
                      {quote}
                    </p>
                  )}
                  <p
                    lang={cited.language ?? undefined}
                    className={cn(
                      "mt-2 whitespace-pre-line font-serif leading-relaxed",
                      quote ? "text-[12.5px] text-muted-foreground" : "text-[14px]",
                    )}
                  >
                    {cited.content}
                  </p>
                  {!citedHere && (
                    <Button variant="outline" size="sm" className="mt-3" onClick={() => changePage(cited.page_start)}>
                      Go to page {cited.page_start}
                    </Button>
                  )}
                  {citedHere && (
                    <p className="mt-3 text-[11.5px] text-muted-foreground">
                      Exact matches are highlighted on the page. If the PDF's text layer differs (scans, unusual
                      fonts), use the passage above.
                    </p>
                  )}
                </div>
              ) : (
                !chunkId && (
                  <div className="mt-3 rounded-lg border border-dashed px-4 py-6 text-center">
                    <Quote className="mx-auto h-4 w-4 text-muted-foreground" strokeWidth={1.6} />
                    <p className="mt-2 text-[13px] font-medium">No passage selected</p>
                    <p className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">
                      Open a citation from an assistant answer to see the exact source passage here.
                    </p>
                  </div>
                )
              )}
            </div>
          )}
        </aside>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete document?"
        description={
          <>
            <span className="font-medium text-foreground">{d?.original_filename}</span>, its stored file and its indexed
            passages will be permanently removed.
          </>
        }
        pending={del.isPending}
        onConfirm={onDelete}
      />
    </div>
  );
}
