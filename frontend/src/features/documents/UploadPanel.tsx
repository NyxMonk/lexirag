import { AlertCircle, Check, FileUp, Loader2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";

import { Button } from "@/components/ui/button";
import { useInvalidateLibrary, useSystemInfo } from "@/hooks/queries";
import { cn, formatBytes } from "@/lib/utils";
import { uploadDocument, type UploadHandle } from "@/services/api";

type UploadState = "queued" | "uploading" | "done" | "error";

interface UploadItem {
  key: string;
  file: File;
  state: UploadState;
  progress: number;
  error?: string;
}

const FALLBACK_MAX_BYTES = 50 * 1024 * 1024;

function preValidate(file: File, maxBytes: number): string | undefined {
  if (!file.name.toLowerCase().endsWith(".pdf")) return "Only PDF files are supported.";
  if (file.type && !["application/pdf", "application/x-pdf"].includes(file.type)) return "This file is not a PDF.";
  if (file.size > maxBytes) return `Larger than the ${formatBytes(maxBytes)} limit.`;
  if (file.size === 0) return "The file is empty.";
  return undefined;
}

export function UploadPanel({ workspaceId, className }: { workspaceId: string; className?: string }) {
  const [items, setItems] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const active = useRef<UploadHandle | null>(null);
  const running = useRef(false);
  const queue = useRef<UploadItem[]>([]);
  const invalidate = useInvalidateLibrary();
  const info = useSystemInfo();
  const maxBytes = info.data?.max_upload_size_bytes ?? FALLBACK_MAX_BYTES;

  const patch = (key: string, update: Partial<UploadItem>) =>
    setItems((all) => all.map((it) => (it.key === key ? { ...it, ...update } : it)));

  // Upload sequentially so progress is meaningful and the local server is not flooded.
  const pump = useCallback(
    async () => {
      if (running.current) return;
      running.current = true;
      let item: UploadItem | undefined;
      while ((item = queue.current.shift())) {
        patch(item.key, { state: "uploading", progress: 0 });
        const key = item.key;
        const handle = uploadDocument(workspaceId, item.file, (p) => patch(key, { progress: p }));
        active.current = handle;
        try {
          await handle.promise;
          patch(key, { state: "done", progress: 1 });
          void invalidate();
        } catch (err) {
          patch(key, { state: "error", error: err instanceof Error ? err.message : "Upload failed." });
        }
      }
      active.current = null;
      running.current = false;
    },
    [workspaceId, invalidate],
  );

  useEffect(
    () => () => {
      queue.current = [];
      active.current?.abort();
    },
    [],
  );

  function addFiles(list: FileList | null) {
    if (!list?.length) return;
    const next: UploadItem[] = Array.from(list).map((file) => {
      const error = preValidate(file, maxBytes);
      return {
        key: `${file.name}-${file.size}-${crypto.randomUUID()}`,
        file,
        state: error ? "error" : "queued",
        progress: 0,
        error,
      };
    });
    setItems((all) => [...next, ...all]);
    queue.current.push(...next.filter((i) => i.state === "queued"));
    void pump();
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  }

  const finished = items.filter((i) => i.state === "done" || i.state === "error");

  return (
    <div className={className}>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex flex-col items-center justify-center rounded-lg border border-dashed bg-surface px-6 py-9 text-center transition-colors duration-150",
          dragging ? "border-foreground/50 bg-accent" : "hover:border-foreground/25",
        )}
      >
        <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg border bg-background shadow-subtle">
          <FileUp className="h-[18px] w-[18px] text-muted-foreground" strokeWidth={1.6} />
        </div>
        <p className="text-[14px] font-medium">Drop PDF files here</p>
        <p className="mt-1 text-[13px] text-muted-foreground">
          or{" "}
          <button
            type="button"
            className="font-medium text-foreground underline underline-offset-4 hover:no-underline"
            onClick={() => inputRef.current?.click()}
          >
            browse your computer
          </button>{" "}
          · up to {formatBytes(maxBytes)} each
        </p>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          className="sr-only"
          data-testid="file-input"
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {items.length > 0 && (
        <div className="mt-3 rounded-lg border bg-surface">
          <ul className="divide-y">
            {items.map((item) => (
              <li key={item.key} className="flex items-center gap-3 px-4 py-2.5 text-[13px]">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center">
                  {item.state === "uploading" || item.state === "queued" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                  ) : item.state === "done" ? (
                    <Check className="h-3.5 w-3.5" />
                  ) : (
                    <AlertCircle className="h-3.5 w-3.5 text-destructive" />
                  )}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="truncate font-medium">{item.file.name}</span>
                    <span className="shrink-0 tabular-nums text-muted-foreground">
                      {item.state === "uploading"
                        ? `${Math.round(item.progress * 100)}%`
                        : item.state === "done"
                          ? "Uploaded"
                          : item.state === "queued"
                            ? "Waiting"
                            : formatBytes(item.file.size)}
                    </span>
                  </div>
                  {item.state === "uploading" && (
                    <div className="mt-1.5 h-[3px] overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full bg-foreground transition-[width] duration-150"
                        style={{ width: `${Math.max(2, item.progress * 100)}%` }}
                      />
                    </div>
                  )}
                  {item.state === "error" && <p className="mt-0.5 text-destructive">{item.error}</p>}
                </div>
              </li>
            ))}
          </ul>
          {finished.length > 0 && (
            <div className="flex items-center justify-between border-t px-4 py-2 text-[12px] text-muted-foreground">
              <span>Uploaded files are processed in the background; status updates automatically.</span>
              <Button
                variant="ghost"
                size="sm"
                className="h-7"
                onClick={() => setItems((all) => all.filter((i) => i.state === "queued" || i.state === "uploading"))}
              >
                <X /> Clear
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
