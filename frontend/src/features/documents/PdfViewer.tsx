import { ChevronLeft, ChevronRight, Loader2, Minus, Plus } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import workerSrc from "pdfjs-dist/build/pdf.worker.min.mjs?url";

import { Button } from "@/components/ui/button";
import { findHighlightRanges, markedHtml } from "@/lib/highlight";

pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;

const ZOOM_STEPS = [0.5, 0.67, 0.8, 1, 1.25, 1.5, 2];

export function PdfViewer({
  url,
  page,
  onPageChange,
  onLoaded,
  highlight,
}: {
  url: string;
  page: number;
  onPageChange: (page: number) => void;
  onLoaded?: (numPages: number) => void;
  /** Passages to highlight on the current page; only exact, contiguous matches are marked. */
  highlight?: string[];
}) {
  const [numPages, setNumPages] = useState(0);
  const [zoomIndex, setZoomIndex] = useState(3);
  const [width, setWidth] = useState(720);
  const [pageInput, setPageInput] = useState(String(page));
  const containerRef = useRef<HTMLDivElement>(null);

  // Character maps and standard fonts are served locally (copied by scripts/copy-pdf-assets.mjs).
  const options = useMemo(
    () => ({ cMapUrl: "/pdfjs/cmaps/", cMapPacked: true, standardFontDataUrl: "/pdfjs/standard_fonts/" }),
    [],
  );

  useEffect(() => setPageInput(String(page)), [page]);

  // pdf.js renders the text layer itself; after each render, wrap only the matched characters
  // in <mark>. The original item text is kept in data-lexi-text and always HTML-escaped.
  const applyHighlights = useCallback(() => {
    const layer = containerRef.current?.querySelector(".react-pdf__Page__textContent");
    if (!layer) return;
    const spans = Array.from(layer.children).filter(
      (el): el is HTMLElement => el instanceof HTMLElement && el.tagName === "SPAN",
    );
    for (const span of spans) {
      if (span.dataset.lexiText === undefined) span.dataset.lexiText = span.textContent ?? "";
    }
    const items = spans.map((span) => span.dataset.lexiText ?? "");
    const ranges = highlight?.length ? findHighlightRanges(items, highlight) : new Map<number, [number, number][]>();
    spans.forEach((span, index) => {
      const r = ranges.get(index);
      if (r) span.innerHTML = markedHtml(items[index], r);
      else if (span.querySelector("mark")) span.textContent = items[index];
    });
    layer.querySelector("mark.lexi-hl")?.scrollIntoView({ block: "center" });
  }, [highlight]);

  useEffect(() => applyHighlights(), [applyHighlights]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.min(entry.contentRect.width - 64, 900)));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const go = (target: number) => {
    if (numPages) onPageChange(Math.min(Math.max(1, target), numPages));
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex h-12 shrink-0 items-center justify-between border-b bg-surface px-3">
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" onClick={() => go(page - 1)} disabled={page <= 1} aria-label="Previous page">
            <ChevronLeft />
          </Button>
          <form
            className="flex items-center gap-1.5 text-[13px] text-muted-foreground"
            onSubmit={(e) => {
              e.preventDefault();
              go(Number.parseInt(pageInput, 10) || page);
            }}
          >
            <input
              aria-label="Page number"
              value={pageInput}
              onChange={(e) => setPageInput(e.target.value.replace(/\D/g, ""))}
              onBlur={() => go(Number.parseInt(pageInput, 10) || page)}
              className="h-7 w-11 rounded-md border bg-background text-center tabular-nums text-foreground focus:outline-none focus:ring-2 focus:ring-ring/15"
            />
            <span className="tabular-nums">of {numPages || "—"}</span>
          </form>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => go(page + 1)}
            disabled={!numPages || page >= numPages}
            aria-label="Next page"
          >
            <ChevronRight />
          </Button>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setZoomIndex((z) => Math.max(0, z - 1))}
            disabled={zoomIndex === 0}
            aria-label="Zoom out"
          >
            <Minus />
          </Button>
          <span className="w-12 text-center text-[12.5px] tabular-nums text-muted-foreground">
            {Math.round(ZOOM_STEPS[zoomIndex] * 100)}%
          </span>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setZoomIndex((z) => Math.min(ZOOM_STEPS.length - 1, z + 1))}
            disabled={zoomIndex === ZOOM_STEPS.length - 1}
            aria-label="Zoom in"
          >
            <Plus />
          </Button>
        </div>
      </div>

      <div ref={containerRef} className="min-h-0 flex-1 overflow-auto bg-muted/60 px-8 py-8">
        <Document
          file={url}
          options={options}
          onLoadSuccess={({ numPages: n }) => {
            setNumPages(n);
            onLoaded?.(n);
            if (page > n) onPageChange(1);
          }}
          loading={
            <div className="flex h-96 items-center justify-center text-sm text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Opening document…
            </div>
          }
          error={
            <div className="mx-auto mt-16 max-w-sm text-center text-sm text-muted-foreground">
              This PDF could not be rendered. It may be damaged or password-protected.
            </div>
          }
          className="flex justify-center"
        >
          <Page
            pageNumber={page}
            width={Math.max(320, width) * ZOOM_STEPS[zoomIndex]}
            className="overflow-hidden rounded-sm shadow-lifted ring-1 ring-black/5"
            onRenderTextLayerSuccess={applyHighlights}
            loading={<div className="h-[900px] w-[640px] animate-pulse rounded-sm bg-background" />}
          />
        </Document>
      </div>
    </div>
  );
}
