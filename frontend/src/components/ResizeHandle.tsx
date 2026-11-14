import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import { cn } from "@/lib/utils";

const STEP = 24;

function readStored(key: string, fallback: number): number {
  try {
    const value = Number(localStorage.getItem(key));
    return Number.isFinite(value) && value > 0 ? value : fallback;
  } catch {
    return fallback;
  }
}

/**
 * Width of a right-hand side panel, resizable by dragging and remembered per browser.
 * `max` is a function so the limit can follow the window size.
 */
export function usePanelWidth(key: string, initial: number, min: number, max: () => number) {
  const [width, setWidthState] = useState(() => readStored(key, initial));
  const clamp = useCallback((w: number) => Math.round(Math.min(Math.max(w, min), Math.max(min, max()))), [min, max]);
  const setWidth = useCallback(
    (w: number) => {
      if (!Number.isFinite(w)) return;
      const next = clamp(w);
      setWidthState(next);
      try {
        localStorage.setItem(key, String(next));
      } catch {
        /* storage unavailable: the width just isn't remembered */
      }
    },
    [clamp, key],
  );
  useEffect(() => {
    const onResize = () => setWidthState((w) => clamp(w));
    onResize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [clamp]);
  return { width, setWidth, reset: () => setWidth(initial) };
}

/** Vertical drag handle placed between a main area and a right-hand panel of the given width. */
export function ResizeHandle({
  width,
  onResize,
  onReset,
  min,
  max,
  label = "Resize panel",
}: {
  width: number;
  onResize: (width: number) => void;
  onReset?: () => void;
  min: number;
  max: number;
  label?: string;
}) {
  const drag = useRef<{ startX: number; startWidth: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  function onPointerDown(e: PointerEvent<HTMLDivElement>) {
    e.preventDefault();
    e.currentTarget.setPointerCapture?.(e.pointerId);
    drag.current = { startX: e.clientX, startWidth: width };
    setDragging(true);
  }
  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    // Dragging left widens the right-hand panel.
    onResize(drag.current.startWidth + (drag.current.startX - e.clientX));
  }
  function onPointerUp(e: PointerEvent<HTMLDivElement>) {
    drag.current = null;
    setDragging(false);
    if (e.currentTarget.hasPointerCapture?.(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
  }
  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "ArrowLeft") onResize(width + STEP);
    else if (e.key === "ArrowRight") onResize(width - STEP);
    else if (e.key === "Home") onResize(max);
    else if (e.key === "End") onResize(min);
    else return;
    e.preventDefault();
  }

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      title="Drag to resize · double-click to reset"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onDoubleClick={onReset}
      onKeyDown={onKeyDown}
      className={cn(
        "group relative z-10 w-0 shrink-0 cursor-col-resize select-none touch-none focus-visible:outline-none",
        // A wide invisible hit area centred on the border line.
        "before:absolute before:inset-y-0 before:-left-1.5 before:w-3 before:content-['']",
      )}
    >
      <div
        className={cn(
          "pointer-events-none absolute inset-y-0 -left-px w-[2px] transition-colors",
          dragging ? "bg-foreground/40" : "bg-transparent group-hover:bg-foreground/20 group-focus-visible:bg-ring",
        )}
      />
      <div
        className={cn(
          "pointer-events-none absolute left-1/2 top-1/2 h-8 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full border bg-surface transition-opacity",
          dragging ? "opacity-100" : "opacity-60 group-hover:opacity-100",
        )}
      />
    </div>
  );
}
