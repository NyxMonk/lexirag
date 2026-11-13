import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { DocumentRecord, FirAnalysis, Workspace } from "@/types/api";

import { baseHandlers, mockApi, renderRoute } from "./utils";

const workspace: Workspace = {
  id: "w1", name: "Criminal law", description: null, document_count: 1, conversation_count: 0,
  created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z",
};

const act: DocumentRecord = {
  id: "d1", workspace_id: "w1", original_filename: "ipc.pdf", file_size: 1000, mime_type: "application/pdf",
  detected_language: "en", language_confidence: 1, language_override: null, effective_language: "en",
  language_status: "detected", processing_status: "completed", processing_error: null, processing_progress: null,
  page_count: 3, chunk_count: 3, processing_started_at: null, processing_completed_at: null,
  created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-01T00:00:00Z",
};

const analysis: FirAnalysis = {
  source: { kind: "text", document_id: null, document_name: null, characters: 120 },
  offence_date: "2023-03-13",
  offence_date_source: "occurrence",
  date_candidates: [
    { date: "2023-03-15", text: "15/03/2023", kind: "report" },
    { date: "2023-03-13", text: "13/03/2023", kind: "occurrence" },
  ],
  applicable_code: "IPC",
  bns_commencement: "2024-07-01",
  charges: [
    {
      section: "498A", code: "IPC", code_source: "explicit", matched_text: "498A/406/34", in_reference: true,
      reference_section: "498A", title: "Husband or relative of husband of a woman subjecting her to cruelty",
      kind: "offence", punishment: "Up to 3 years and fine", cognizable: "cognizable", bailable: "non-bailable",
      court: "Magistrate of the first class", note: null,
      corresponds_to: [{ code: "BNS", section: "85", title: "Husband or relative of husband of a woman subjecting her to cruelty" }],
    },
    {
      section: "34", code: "IPC", code_source: "explicit", matched_text: "498A/406/34", in_reference: true,
      reference_section: "34", title: "Acts done by several persons in furtherance of common intention",
      kind: "liability", punishment: "Same as the main offence", cognizable: "depends", bailable: "depends",
      court: "Same as the main offence", note: "Not an offence by itself.", corresponds_to: [],
    },
    {
      section: "999", code: "IPC", code_source: "explicit", matched_text: "999", in_reference: false,
      reference_section: null, title: null, kind: null, punishment: null, cognizable: null, bailable: null,
      court: null, note: null, corresponds_to: [],
    },
  ],
  reference: { validated: false, sources: ["CrPC First Schedule"], caveats: ["Not yet checked against the official schedules."] },
  warnings: [],
  disclaimer: "Automated reading of the FIR against a reference table. Not legal advice.",
};

describe("FIR explainer", () => {
  it("analyses pasted text and shows the backend's charge card without inventing data", async () => {
    let sent: Record<string, unknown> | null = null;
    mockApi({
      ...baseHandlers,
      "GET /workspaces": () => [workspace],
      "GET /documents": () => [act],
      "POST /fir/analyze": (_url, init) => {
        sent = JSON.parse(String(init?.body));
        return new Response(JSON.stringify(analysis), { status: 200 });
      },
    });
    renderRoute("/fir");
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "English · IPC (2023)" }));
    expect(screen.getByText(/Synthetic sample: invented names/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Analyse FIR/ }));

    expect(await screen.findByText("Indian Penal Code, 1860")).toBeInTheDocument();
    expect(sent).toMatchObject({ offence_date: null });
    expect((sent as unknown as { text: string }).text).toContain("498A/406/34 IPC");

    expect(screen.getByText("§ 498A")).toBeInTheDocument();
    expect(screen.getByText("non-bailable")).toBeInTheDocument();
    expect(screen.getByText(/Now under BNS/)).toBeInTheDocument();
    expect(screen.getByText(/unofficial correspondence/)).toBeInTheDocument();
    expect(screen.getByText(/not in the reference table yet/)).toBeInTheDocument();
    expect(screen.getByText("Reference data, not yet verified")).toBeInTheDocument();
    // No LLM is configured in the base handlers, so the explanation is blocked with a reason.
    expect(screen.getByRole("button", { name: /Explain with citations/ })).toBeDisabled();
  });

  it("re-runs with a chosen date from the FIR", async () => {
    const bodies: Record<string, unknown>[] = [];
    mockApi({
      ...baseHandlers,
      "GET /workspaces": () => [workspace],
      "GET /documents": () => [act],
      "POST /fir/analyze": (_url, init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return new Response(JSON.stringify(analysis), { status: 200 });
      },
    });
    renderRoute("/fir");
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("FIR text"), "u/s 498A IPC");
    await user.click(screen.getByRole("button", { name: /Analyse FIR/ }));
    await user.click(await screen.findByRole("button", { name: /15 Mar 2023 \(report\)/ }));
    await waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1]).toMatchObject({ offence_date: "2023-03-15" });
  });
});
