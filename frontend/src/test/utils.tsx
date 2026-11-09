import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, useRoutes } from "react-router-dom";
import { vi } from "vitest";

import { createQueryClient, Providers, routes } from "@/App";

type Handler = (url: URL, init?: RequestInit) => unknown;

/** Route fetch calls to handlers keyed by "METHOD /path". Unknown routes fail the test. */
export function mockApi(handlers: Record<string, Handler>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.pathname.replace(/^\/api\/v1/, "");
    const handler = handlers[`${method} ${path}`];
    if (!handler) throw new Error(`Unhandled request: ${method} ${path}`);
    const result = handler(url, init);
    if (result instanceof Response) return result;
    return new Response(JSON.stringify(result), {
      status: method === "POST" ? 201 : 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

export function renderRoute(path: string) {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false, staleTime: 0 } });
  // A plain MemoryRouter avoids jsdom/undici AbortSignal clashes in the data router.
  return render(
    <Providers client={client}>
      <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AppRoutes />
      </MemoryRouter>
    </Providers>,
  );
}

function AppRoutes() {
  return useRoutes(routes);
}

export function renderWithProviders(ui: ReactElement) {
  const client = createQueryClient();
  return render(<Providers client={client}>{ui}</Providers>);
}

export const baseHandlers: Record<string, Handler> = {
  "GET /health": () => ({ status: "ok", version: "0.1.0", database: { status: "ok", pgvector: true, pgvector_version: "0.8.0" } }),
  "GET /system/info": () => ({
    name: "LexiRAG",
    version: "0.1.0",
    environment: "test",
    supported_languages: [],
    accepted_mime_types: ["application/pdf"],
    max_upload_size_bytes: 50 * 1024 * 1024,
    model_provider: { provider: "none", model: null, configured: false },
    retrieval_engine_available: true,
    answering_available: false,
  }),
  "GET /settings/models": () => ({
    embedding: { model: "BAAI/bge-m3", enabled: true, downloaded: true, loaded: false, device: null, dimension: 1024 },
    reranker: { model: "BAAI/bge-reranker-v2-m3", enabled: true, downloaded: true, loaded: false, device: null },
    generation: { provider: "none", model: null, configured: false },
    ocr: { enabled: true, available: false, version: null, installed_languages: [], missing_languages: [], message: "Tesseract OCR is not installed." },
    retrieval: { dense_top_k: 30, bm25_top_k: 30, rrf_k: 60, rerank_candidates: 16, final_top_k: 6, chunk_target_tokens: 700, chunk_overlap_tokens: 120 },
    models_allow_download: false,
    processing_queue: 0,
  }),
  "GET /conversations": () => [],
};
