import { cn } from "@/lib/utils";
import type { DocumentRecord, ProcessingStatus } from "@/types/api";

const STATUS: Record<ProcessingStatus, { label: string; hint: string; dot: string }> = {
  uploaded: {
    label: "Uploaded",
    hint: "File stored. It has not been processed yet.",
    dot: "bg-muted-foreground/50",
  },
  queued: { label: "Queued", hint: "Waiting for the processing worker.", dot: "bg-amber-500 animate-pulse" },
  extracting: { label: "Extracting text", hint: "Reading text page by page.", dot: "bg-amber-500 animate-pulse" },
  chunking: { label: "Chunking", hint: "Splitting text at section and paragraph boundaries.", dot: "bg-amber-500 animate-pulse" },
  embedding: { label: "Generating embeddings", hint: "Computing multilingual embeddings.", dot: "bg-amber-500 animate-pulse" },
  indexing: { label: "Indexing", hint: "Storing passages and vectors.", dot: "bg-amber-500 animate-pulse" },
  completed: { label: "Ready", hint: "Indexed and searchable by the assistant.", dot: "bg-emerald-600" },
  failed: { label: "Failed", hint: "Processing failed.", dot: "bg-destructive" },
};

export function StatusBadge({
  status,
  progress,
  className,
}: {
  status: ProcessingStatus;
  progress?: DocumentRecord["processing_progress"];
  className?: string;
}) {
  const s = STATUS[status];
  const showProgress = status === "embedding" && progress && progress.total > 0;
  return (
    <span
      title={s.hint}
      className={cn(
        "inline-flex h-6 items-center gap-1.5 whitespace-nowrap rounded-full border bg-surface px-2.5 text-[12px] font-medium text-foreground/80",
        className,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} aria-hidden />
      {s.label}
      {showProgress && (
        <span className="tabular-nums text-muted-foreground">
          {Math.round((progress.done / progress.total) * 100)}%
        </span>
      )}
    </span>
  );
}

export function statusHint(status: ProcessingStatus) {
  return STATUS[status].hint;
}
