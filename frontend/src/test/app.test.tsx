import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { DocumentRecord, Workspace } from "@/types/api";

import { baseHandlers, mockApi, renderRoute } from "./utils";

const workspace: Workspace = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "Tenancy dispute",
  description: "Pune matters",
  document_count: 1,
  conversation_count: 0,
  created_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-02T10:00:00Z",
};

const doc: DocumentRecord = {
  id: "22222222-2222-2222-2222-222222222222",
  workspace_id: workspace.id,
  original_filename: "Lease Agreement.pdf",
  file_size: 204800,
  mime_type: "application/pdf",
  detected_language: null,
  language_confidence: null,
  language_override: null,
  effective_language: null,
  language_status: null,
  processing_status: "uploaded",
  processing_error: null,
  processing_progress: null,
  page_count: null,
  chunk_count: null,
  processing_started_at: null,
  processing_completed_at: null,
  created_at: "2026-10-02T10:00:00Z",
  updated_at: "2026-10-02T10:00:00Z",
};

const readyDoc: DocumentRecord = {
  ...doc,
  detected_language: "en",
  effective_language: "en",
  language_status: "detected",
  processing_status: "completed",
  page_count: 3,
  chunk_count: 6,
};

describe("Dashboard", () => {
  it("shows onboarding for a new user", async () => {
    mockApi({ ...baseHandlers, "GET /workspaces": () => [], "GET /documents": () => [] });
    renderRoute("/");
    expect(await screen.findByRole("button", { name: /create your first workspace/i })).toBeInTheDocument();
    expect(screen.getByText("No documents yet")).toBeInTheDocument();
    expect(screen.getByText("Local server connected")).toBeInTheDocument();
  });

  it("lists recent documents with honest status", async () => {
    mockApi({ ...baseHandlers, "GET /workspaces": () => [workspace], "GET /documents": () => [doc] });
    renderRoute("/");
    expect(await screen.findByText("Lease Agreement.pdf")).toBeInTheDocument();
    // Unprocessed files are never shown as ready.
    expect(screen.getAllByText("Uploaded").length).toBeGreaterThan(0);
    expect(screen.getByText("0 / 1")).toBeInTheDocument();
  });

  it("shows an error state when the API is unreachable", async () => {
    mockApi({
      ...baseHandlers,
      "GET /workspaces": () => new Response(JSON.stringify({ error: { code: "internal_error", message: "Boom" } }), { status: 500 }),
      "GET /documents": () => [],
    });
    renderRoute("/");
    expect(await screen.findByText("Boom")).toBeInTheDocument();
  });
});

describe("Workspaces", () => {
  it("creates a workspace through the API and opens it", async () => {
    const created: Workspace = { ...workspace, id: "33333333-3333-3333-3333-333333333333", name: "किरायेदारी विवाद", document_count: 0 };
    let workspaces: Workspace[] = [];
    const fetchMock = mockApi({
      ...baseHandlers,
      "GET /workspaces": () => workspaces,
      "POST /workspaces": (_url, init) => {
        const body = JSON.parse(String(init?.body));
        expect(body).toEqual({ name: "किरायेदारी विवाद", description: null });
        workspaces = [created];
        return created;
      },
      [`GET /workspaces/${created.id}`]: () => created,
      "GET /documents": () => [],
    });

    renderRoute("/workspaces");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /new workspace/i }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Name"), "किरायेदारी विवाद");
    await user.click(within(dialog).getByRole("button", { name: /create workspace/i }));

    expect(await screen.findByRole("heading", { level: 1, name: "किरायेदारी विवाद" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/workspaces"), expect.objectContaining({ method: "POST" }));
  });

  it("shows the empty state when there are no workspaces", async () => {
    mockApi({ ...baseHandlers, "GET /workspaces": () => [] });
    renderRoute("/workspaces");
    expect(await screen.findByText("No workspaces yet")).toBeInTheDocument();
  });

  it("lists documents in a workspace and deletes one after confirmation", async () => {
    let docs = [doc];
    mockApi({
      ...baseHandlers,
      "GET /workspaces": () => [workspace],
      [`GET /workspaces/${workspace.id}`]: () => workspace,
      "GET /documents": () => docs,
      [`DELETE /documents/${doc.id}`]: () => {
        docs = [];
        return new Response(null, { status: 204 });
      },
    });
    renderRoute(`/workspaces/${workspace.id}`);
    const user = userEvent.setup();

    expect(await screen.findByText("Lease Agreement.pdf")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /actions for lease agreement.pdf/i }));
    await user.click(await screen.findByRole("menuitem", { name: /delete/i }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));

    expect(await screen.findByText("No documents in this workspace")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Lease Agreement.pdf" })).not.toBeInTheDocument();
    expect(screen.getByText("Document deleted")).toBeInTheDocument();
  });
});

describe("Assistant", () => {
  it("explains why answering is unavailable instead of faking it", async () => {
    mockApi({ ...baseHandlers, "GET /workspaces": () => [workspace], "GET /documents": () => [readyDoc] });
    renderRoute("/assistant");
    expect(await screen.findByText(/No answer provider is configured/i)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("sends a question and renders the cited answer from the API", async () => {
    const conversation = { id: "c1", workspace_id: workspace.id, title: "New conversation", message_count: 0,
      created_at: doc.created_at, updated_at: doc.created_at };
    const citation = {
      marker: 1, chunk_id: "chunk-1", document_id: readyDoc.id, document_name: "Lease Agreement.pdf",
      page_start: 3, page_end: 3, section_title: "Clause 9 - Termination", source_language: "en",
      quoted_text: "Either party may terminate this agreement by giving sixty (60) days' written notice.",
      quote_verified: true,
    };
    const userMessage = { id: "m1", conversation_id: "c1", role: "user", content: "समाप्ति की शर्तें क्या हैं?",
      language: "hi", citations: null, evidence_sufficient: null, details: null, created_at: doc.created_at };
    const assistantMessage = { id: "m2", conversation_id: "c1", role: "assistant",
      content: "कोई भी पक्ष 60 दिन की लिखित सूचना देकर अनुबंध समाप्त कर सकता है [1]।", language: "hi",
      citations: [citation], evidence_sufficient: true,
      details: { answer_source: "model", warnings: [], generation: { provider: "gemini", model: "gemini-3.5-flash", duration_ms: 2100 } },
      created_at: doc.created_at };
    let sent: unknown = null;
    mockApi({
      ...baseHandlers,
      "GET /system/info": () => ({ ...(baseHandlers["GET /system/info"] as () => object)(),
        retrieval_engine_available: true, answering_available: true,
        model_provider: { provider: "gemini", model: "gemini-3.5-flash", configured: true } }),
      "GET /workspaces": () => [workspace],
      "GET /documents": () => [readyDoc],
      "POST /chat/messages": (_u, init) => {
        sent = JSON.parse(String(init?.body));
        return { conversation_id: "c1", user_message: userMessage, assistant_message: assistantMessage, answer: {} };
      },
      "GET /chat/conversations/c1": () => ({ ...conversation, messages: sent ? [userMessage, assistantMessage] : [] }),
    });
    renderRoute("/assistant");
    const user = userEvent.setup();
    const box = await screen.findByRole("textbox", { name: "Message" });
    await waitFor(() => expect(box).toBeEnabled());
    await user.type(box, "समाप्ति की शर्तें क्या हैं?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText(/60 दिन की लिखित सूचना/)).toBeInTheDocument();
    expect(sent).toEqual({
      content: "समाप्ति की शर्तें क्या हैं?",
      document_ids: null,
      response_language: "match",
      workspace_id: workspace.id,
    });
    expect(screen.getByText("Lease Agreement.pdf")).toBeInTheDocument();
    expect(screen.getByText(/Exact quotation from the document/)).toBeInTheDocument();
    expect(screen.getByText(/gemini-3.5-flash/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1" })).toHaveAttribute("title", "Lease Agreement.pdf, p. 3");
  });
});

describe("Settings", () => {
  it("never shows secrets and reports provider state", async () => {
    mockApi({ ...baseHandlers, "GET /workspaces": () => [] });
    renderRoute("/settings");
    expect(await screen.findByText("Not configured")).toBeInTheDocument();
    expect(screen.getByText("Not set")).toBeInTheDocument();
  });
});
