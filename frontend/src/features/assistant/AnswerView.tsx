import { AlertTriangle, BadgeCheck, FileText, Info, Quote } from "lucide-react";
import { Fragment, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { languageLabel } from "@/lib/languages";
import { cn } from "@/lib/utils";
import type { Citation, Message } from "@/types/api";

export function citationHref(c: Citation) {
  return `/documents/${c.document_id}?page=${c.quote_page ?? c.page_start}&chunk=${c.chunk_id}`;
}

/** Navigation state: the verified quotation is highlighted instead of the whole passage. */
export function citationState(c: Citation) {
  return { quote: c.quote_verified ? c.quoted_text : null };
}

function pages(c: Citation) {
  if (c.quote_page) return `p. ${c.quote_page}`;
  return c.page_start === c.page_end ? `p. ${c.page_start}` : `pp. ${c.page_start}–${c.page_end}`;
}

/** Minimal emphasis support: **bold** becomes <strong>. Everything else stays plain text. */
function renderInline(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <strong key={`${keyPrefix}-${i}`} className="font-semibold">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <Fragment key={`${keyPrefix}-${i}`}>{part}</Fragment>
    ),
  );
}

/** Answer text with [n] markers turned into citation links. Nothing is added that the backend did not return. */
function AnswerText({ text, citations }: { text: string; citations: Citation[] }) {
  const navigate = useNavigate();
  const byMarker = new Map(citations.map((c) => [c.marker, c]));
  const paragraphs = text.split(/\n{2,}/);
  return (
    <>
      {paragraphs.map((para, i) => {
        const parts: ReactNode[] = [];
        let last = 0;
        for (const match of para.matchAll(/\[(\d+)\]/g)) {
          const citation = byMarker.get(Number(match[1]));
          parts.push(...renderInline(para.slice(last, match.index), `${i}-${last}`));
          parts.push(
            citation ? (
              <button
                key={`${i}-${match.index}`}
                type="button"
                onClick={() => navigate(citationHref(citation), { state: citationState(citation) })}
                title={`${citation.document_name}, ${pages(citation)}`}
                className="mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded border bg-surface px-1 align-middle text-[10.5px] font-semibold tabular-nums text-foreground transition-colors hover:border-foreground/40 hover:bg-accent"
              >
                {citation.marker}
              </button>
            ) : (
              match[0]
            ),
          );
          last = (match.index ?? 0) + match[0].length;
        }
        parts.push(...renderInline(para.slice(last), `${i}-end`));
        return (
          <p key={i} className="whitespace-pre-line">
            {parts.map((part, j) => (
              <Fragment key={j}>{part}</Fragment>
            ))}
          </p>
        );
      })}
    </>
  );
}

export function SourceCard({ citation }: { citation: Citation }) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => navigate(citationHref(citation), { state: citationState(citation) })}
      className="group flex w-full gap-3 rounded-lg border bg-card p-3.5 text-left shadow-subtle transition-[border-color,box-shadow] hover:border-foreground/25 hover:shadow-lifted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="flex h-5 min-w-5 shrink-0 items-center justify-center rounded border text-[10.5px] font-semibold tabular-nums">
        {citation.marker}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 text-[12.5px] font-medium">
          <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" strokeWidth={1.6} />
          <span className="truncate">{citation.document_name}</span>
          <span className="shrink-0 text-muted-foreground">· {pages(citation)}</span>
        </span>
        {citation.section_title && (
          <span className="mt-0.5 block truncate text-[12px] text-muted-foreground">{citation.section_title}</span>
        )}
        <span
          lang={citation.source_language ?? undefined}
          className="mt-2 line-clamp-4 block border-l-2 pl-3 font-serif text-[14px] leading-relaxed text-foreground/85"
        >
          {citation.quoted_text}
        </span>
        <span className="mt-2 flex items-center gap-1 text-[11px] text-muted-foreground">
          {citation.quote_verified ? (
            <>
              <BadgeCheck className="h-3 w-3" /> Exact quotation from the document
            </>
          ) : (
            <>
              <Quote className="h-3 w-3" /> Stored passage (the model's quote could not be matched verbatim)
            </>
          )}
          {citation.source_language && <span>· {languageLabel(citation.source_language)}</span>}
        </span>
      </span>
    </button>
  );
}

export function AssistantMessage({ message }: { message: Message }) {
  const citations = message.citations ?? [];
  const details = message.details ?? {};
  const retrieval = details.retrieval;
  const generation = details.generation;
  const insufficient = message.evidence_sufficient === false;

  return (
    <div className="space-y-4">
      {insufficient && (
        <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/[0.06] px-3 py-2 text-[12.5px]">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
          <span>The selected documents do not contain enough evidence to answer this fully.</span>
        </div>
      )}
      <div lang={message.language ?? undefined} className="space-y-3 text-[15px] leading-[1.7]">
        <AnswerText text={message.content} citations={citations} />
      </div>
      {citations.length > 0 && (
        <div>
          <p className="label-caps mb-2">Sources</p>
          <div className="grid gap-2">
            {citations.map((c) => (
              <SourceCard key={c.marker} citation={c} />
            ))}
          </div>
        </div>
      )}
      {(details.warnings?.length ?? 0) > 0 && (
        <ul className="space-y-1 text-[12px] text-muted-foreground">
          {details.warnings!.map((w) => (
            <li key={w} className="flex gap-1.5">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> {w}
            </li>
          ))}
        </ul>
      )}
      <p className={cn("flex flex-wrap gap-x-2 text-[11.5px] text-muted-foreground")}>
        {message.language && <span>Answer in {languageLabel(message.language)}</span>}
        {retrieval && (
          <span>
            · {retrieval.passages.length} passages from {retrieval.fused_candidates} candidates
            {retrieval.reranked ? ", reranked" : ""}
          </span>
        )}
        {generation && (
          <span>
            · {generation.model} · {(generation.duration_ms / 1000).toFixed(1)} s
          </span>
        )}
        {details.answer_source === "system" && <span>· no passages found, no model call</span>}
        <span>· Information from your documents, not legal advice.</span>
      </p>
    </div>
  );
}
