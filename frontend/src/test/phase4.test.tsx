import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { findHighlightRanges, highlightPassages, markedHtml } from "@/lib/highlight";
import type { DocumentRecord, Workspace } from "@/types/api";

import { baseHandlers, mockApi, renderRoute } from "./utils";

// pdf.js cannot run in jsdom; the stub reports the page and passages the viewer asks for.
vi.mock("@/features/documents/PdfViewer", () => ({
  PdfViewer: ({ page, highlight }: { page: number; highlight?: string[] }) => (
    <div data-testid="pdf">
      page {page} · highlight {highlight?.length ? highlight.join(" | ") : "none"}
    </div>
  ),
}));

const workspace: Workspace = {
  id: "w1", name: "Matters", description: null, document_count: 2, conversation_count: 0,
  created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z",
};

function doc(id: string, name: string, status: DocumentRecord["processing_status"] = "completed"): DocumentRecord {
  return {
    id, workspace_id: "w1", original_filename: name, file_size: 1000, mime_type: "application/pdf",
    detected_language: "en", language_confidence: 1, language_override: null, effective_language: "en",
    language_status: "detected", processing_status: status, processing_error: null, processing_progress: null,
    page_count: 3, chunk_count: 3, processing_started_at: null, processing_completed_at: null,
    created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z",
  };
}

const lease = doc("d1", "lease.pdf");
const tenancy = doc("d2", "tenancy.pdf");
const pending = doc("d3", "scan.pdf", "embedding");

const citation = {
  marker: 1, chunk_id: "c1", document_id: "d1", document_name: "lease.pdf", page_start: 2, page_end: 3,
  quote_page: 3, section_title: "Clause 9 - Termination", source_language: "en",
  quoted_text: "Either party may terminate this agreement by giving sixty (60) days' written notice.",
  quote_verified: true,
};

const answering = {
  ...baseHandlers,
  "GET /system/info": () => ({
    ...(baseHandlers["GET /system/info"] as () => object)(),
    answering_available: true,
    model_provider: { provider: "gemini", model: "gemini-3.5-flash", configured: true },
  }),
  "GET /workspaces": () => [workspace],
  "GET /documents": () => [lease, tenancy, pending],
};

function exchange(body: { content: string; response_language: string }) {
  const message = (id: string, role: string, content: string, extra = {}) => ({
    id, conversation_id: "conv1", role, content, language: "en", citations: null, evidence_sufficient: null,
    details: null, created_at: "2026-11-01T00:00:00Z", ...extra,
  });
  return {
    conversation_id: "conv1",
    user_message: message("m1", "user", body.content),
    assistant_message: message("m2", "assistant", "Sixty days' notice [1].", {
      citations: [citation], evidence_sufficient: true, language: body.response_language,
    }),
    answer: {},
  };
}

async function ask(text: string) {
  const user = userEvent.setup();
  const box = await screen.findByRole("textbox", { name: "Message" });
  await waitFor(() => expect(box).toBeEnabled());
  await user.type(box, text);
  await user.click(screen.getByRole("button", { name: "Send" }));
  return user;
}

describe("Assistant scope and language", () => {
  it("sends the selected documents and response language to the backend", async () => {
    let sent: Record<string, unknown> | null = null;
    mockApi({
      ...answering,
      "POST /chat/messages": (_u, init) => {
        sent = JSON.parse(String(init?.body));
        return exchange(sent as never);
      },
      "GET /chat/conversations/conv1": () => ({ id: "conv1", workspace_id: "w1", title: "Notice?", created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z",
        messages: [exchange(sent as never).user_message, exchange(sent as never).assistant_message] }),
    });
    renderRoute("/assistant?workspace=w1");
    const user = userEvent.setup();

    // Scope: pick two ready documents; the one still processing cannot be selected.
    const scope = await screen.findByRole("button", { name: "Scope" });
    await waitFor(() => expect(scope).toHaveTextContent("All ready documents (2)"));
    await user.click(scope);
    await user.click(await screen.findByRole("menuitem", { name: /lease\.pdf/ }));
    await user.click(screen.getByRole("menuitem", { name: /tenancy\.pdf/ }));
    expect(screen.getByRole("menuitem", { name: /scan\.pdf/ })).toHaveAttribute("data-disabled");
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "Scope" })).toHaveTextContent("2 documents");

    // Response language: Hindi.
    await user.click(screen.getByRole("combobox", { name: "Answer in" }));
    await user.click(await screen.findByRole("option", { name: /Hindi/ }));

    await ask("What notice ends the lease?");
    await waitFor(() => expect(sent).not.toBeNull());
    expect(sent).toEqual({
      content: "What notice ends the lease?",
      document_ids: ["d1", "d2"],
      response_language: "hi",
      workspace_id: "w1",
    });
    expect(await screen.findByText("Clause 9 - Termination")).toBeInTheDocument();
  });

  it("keeps the question and creates no conversation when answering fails", async () => {
    let calls = 0;
    const conversations: unknown[] = [];
    mockApi({
      ...answering,
      "GET /conversations": () => conversations,
      "POST /chat/messages": () => {
        calls += 1;
        return new Response(
          JSON.stringify({ error: { code: "generation_failed", message: "Gemini is temporarily unavailable (HTTP 503)." } }),
          { status: 502 },
        );
      },
    });
    renderRoute("/assistant?workspace=w1");
    await ask("What is the rent?");

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(/temporarily unavailable/)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("What is the rent?");
    expect(screen.getByText(/Questions you ask in this workspace are saved here/)).toBeInTheDocument();
    expect(calls).toBe(1);

    await userEvent.setup().click(within(alert).getByRole("button", { name: /Retry/ }));
    await waitFor(() => expect(calls).toBe(2));
  });

  it("hides empty conversations left by earlier failures", async () => {
    mockApi({
      ...answering,
      "GET /conversations": () => [
        { id: "a", workspace_id: "w1", title: "Saved question", message_count: 2, created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z" },
        { id: "b", workspace_id: "w1", title: "New conversation", message_count: 0, created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z" },
      ],
    });
    renderRoute("/assistant?workspace=w1");
    expect(await screen.findByText("Saved question")).toBeInTheDocument();
    expect(screen.queryByText("New conversation")).not.toBeInTheDocument();
  });
});

describe("Citation navigation", () => {
  it("opens the cited document at the quote's page and shows the original passage", async () => {
    mockApi({
      ...answering,
      "GET /conversations": () => [{ id: "conv1", workspace_id: "w1", title: "Notice?", message_count: 2, created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z" }],
      "GET /chat/conversations/conv1": () => ({
        id: "conv1", workspace_id: "w1", title: "Notice?", created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z",
        messages: [exchange({ content: "Notice?", response_language: "en" }).user_message,
          exchange({ content: "Notice?", response_language: "en" }).assistant_message],
      }),
      "GET /documents/d1": () => lease,
      "GET /workspaces/w1": () => workspace,
      "GET /documents/d1/chunks/c1": () => ({
        id: "c1", document_id: "d1", chunk_index: 1, page_start: 2, page_end: 3, language: "en",
        section_title: "4. Maintenance", token_count: 50, created_at: "2026-11-01T00:00:00Z",
        content: "Repairs are the landlord's duty.\n\nEither party may terminate this agreement by giving sixty (60) days' written notice.",
      }),
    });
    renderRoute("/assistant?workspace=w1&conversation=conv1");
    const user = userEvent.setup();
    await user.click(await screen.findByTitle("lease.pdf, p. 3"));

    const pdf = await screen.findByTestId("pdf");
    expect(pdf).toHaveTextContent("page 3");
    // The verified quote (not the whole chunk) is what the viewer highlights.
    expect(pdf).toHaveTextContent(`highlight ${citation.quoted_text}`);
    expect(screen.getByText(/Pages 2–3 · 4. Maintenance/)).toBeInTheDocument();
    expect(screen.getByText(/Repairs are the landlord.s duty/)).toBeInTheDocument(); // original passage shown
  });
});

describe("Document summary panel", () => {
  it("requests a summary in the chosen language and renders its citations", async () => {
    let sent: unknown = null;
    mockApi({
      ...answering,
      "GET /documents/d1": () => lease,
      "GET /workspaces/w1": () => workspace,
      "POST /documents/d1/summary": (_u, init) => {
        sent = JSON.parse(String(init?.body));
        return {
          answer: "Un bail résidentiel synthétique.\n\n- Préavis de soixante jours [1].",
          language: "fr", query_language: null, query_language_status: "n/a", evidence_sufficient: true,
          answer_source: "model", citations: [citation], retrieval: null,
          generation: { provider: "gemini", model: "gemini-3.5-flash", duration_ms: 1200 }, warnings: [], disclaimer: "",
        };
      },
    });
    renderRoute("/documents/d1");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("combobox", { name: "Summary language" }));
    await user.click(await screen.findByRole("option", { name: /French/ }));
    await user.click(screen.getByRole("button", { name: /Summarise/ }));

    expect(await screen.findByText(/Préavis de soixante jours/)).toBeInTheDocument();
    expect(sent).toEqual({ response_language: "fr" });
    expect(screen.getByTitle("lease.pdf, p. 3")).toBeInTheDocument();
    expect(screen.getByText("Clause 9 - Termination")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Regenerate" })).toBeInTheDocument();
  });

  it("shows the backend error when no provider is configured", async () => {
    mockApi({
      ...answering,
      "GET /documents/d1": () => lease,
      "GET /workspaces/w1": () => workspace,
      "POST /documents/d1/summary": () =>
        new Response(JSON.stringify({ error: { code: "llm_not_configured", message: "No answer-generation provider is configured." } }), { status: 503 }),
    });
    renderRoute("/documents/d1");
    await userEvent.setup().click(await screen.findByRole("button", { name: /Summarise/ }));
    expect(await screen.findByText("No answer-generation provider is configured.")).toBeInTheDocument();
  });
});

describe("Citation highlighting", () => {
  const marked = (items: string[], passage: string) => {
    const ranges = findHighlightRanges(items, [passage]);
    return items.map((item, i) => (ranges.get(i) ?? []).map(([a, b]) => item.normalize("NFC").slice(a, b)).join("")).join("");
  };

  it("marks only the quoted sentence when pdf.js puts two sentences in one item (real pdf.js output)", () => {
    // Text-layer items captured from pdf.js for synthetic_tenancy_hi.pdf page 2 (visual-order ि).
    const items = [
      "धारा 4 — अनुबंध की समा",
      "कोई भी पक्ष तीस िदन की िल\u0000खत सू चना देकर यह अनुबंध समाप्त कर सकता है । यिद िकरायेदारलगातार तीन महीने िकराया नहीं देता, तो मकान मािलक तुरंत अनुबंध समाप्त कर सकता है ।",
    ];
    const text = marked(items, "कोई भी पक्ष तीस दिन की लिखित सूचना देकर यह अनुबंध समाप्त कर सकता है।");
    expect(text.startsWith("कोईभीपक्ष")).toBe(true);
    expect(text).not.toContain("मकान"); // the following sentence in the same item stays unmarked
    expect(findHighlightRanges(items, ["कोई भी पक्ष तीस दिन की लिखित सूचना देकर यह अनुबंध समाप्त कर सकता है।"]).has(0)).toBe(false);
  });

  it("joins fragments split mid-word", () => {
    const items = ["Either pa", "rty may termi", "nate this agreement.", " Rent is due monthly."];
    expect(marked(items, "Either party may terminate this agreement.")).toBe("Eitherpartymayterminatethisagreement.");
  });

  it("highlights nothing without a contiguous match, and ignores tiny passages", () => {
    const items = ["Rent is due monthly.", "Either party may terminate."];
    expect(findHighlightRanges(items, ["A sentence that is not on this page at all."]).size).toBe(0);
    expect(findHighlightRanges(items, ["Rent"]).size).toBe(0);
    expect(findHighlightRanges(["assess sessions"], ["aeeion"]).size).toBe(0); // letters are never ignored
  });

  it("escapes PDF text when wrapping matches", () => {
    expect(markedHtml("a <b> & c", [[2, 5]])).toBe('a <mark class="lexi-hl">&lt;b&gt;</mark> &amp; c');
  });

  it("uses the verified quote, otherwise each paragraph of the stored passage", () => {
    expect(highlightPassages("quote text", "a\n\nb")).toEqual(["quote text"]);
    expect(highlightPassages(null, "first paragraph\n\nsecond paragraph")).toEqual(["first paragraph", "second paragraph"]);
    expect(highlightPassages(null, null)).toEqual([]);
  });
});
