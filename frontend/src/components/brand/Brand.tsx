import { cn } from "@/lib/utils";

/**
 * The LexiRAG mark: an "L" (the law, the page margin) with a detached square —
 * the cited passage that retrieval lifts out of the document.
 */
export function BrandMark({ className, title = "LexiRAG" }: { className?: string; title?: string }) {
  return (
    <svg viewBox="0 0 32 32" role="img" aria-label={title} className={cn("h-7 w-7 shrink-0", className)}>
      <rect width="32" height="32" rx="7" className="fill-foreground" />
      <rect x="9" y="7" width="3.5" height="18" className="fill-background" />
      <rect x="9" y="21.5" width="14" height="3.5" className="fill-background" />
      <rect x="18.5" y="7" width="4.5" height="4.5" className="fill-background" />
    </svg>
  );
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-baseline select-none leading-none", className)} aria-label="LexiRAG">
      <span className="font-serif text-[21px] font-medium tracking-[-0.02em]">Lexi</span>
      <span className="ml-[1px] text-[12.5px] font-semibold tracking-[0.14em]">RAG</span>
    </span>
  );
}

export function BrandLockup({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <BrandMark />
      <Wordmark />
    </span>
  );
}
