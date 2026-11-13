import { API_BASE_URL } from "@/lib/config";
import type {
  AnswerResponse,
  ApiErrorBody,
  Chunk,
  Conversation,
  ConversationDetail,
  DocumentQuery,
  DocumentRecord,
  DocumentStatus,
  FirAnalysis,
  FirAnalyzeRequest,
  HealthResponse,
  MessageCreate,
  MessageExchange,
  ModelsInfo,
  QueryRequest,
  SystemInfo,
  Workspace,
  WorkspaceCreate,
} from "@/types/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const NETWORK_MESSAGE = "Cannot reach the LexiRAG API. Check that the backend is running.";

function toApiError(status: number, body: unknown): ApiError {
  const err = (body as Partial<ApiErrorBody> | null)?.error;
  if (err?.message) return new ApiError(err.message, status, err.code ?? "error", err.details);
  return new ApiError(`Request failed with status ${status}.`, status, "http_error");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(NETWORK_MESSAGE, 0, "network_error");
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) throw toApiError(response.status, body);
  return body as T;
}

function json(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  systemInfo: () => request<SystemInfo>("/system/info"),
  models: () => request<ModelsInfo>("/settings/models"),

  listWorkspaces: () => request<Workspace[]>("/workspaces"),
  getWorkspace: (id: string) => request<Workspace>(`/workspaces/${id}`),
  createWorkspace: (data: WorkspaceCreate) => request<Workspace>("/workspaces", json("POST", data)),
  deleteWorkspace: (id: string) => request<void>(`/workspaces/${id}`, { method: "DELETE" }),

  listDocuments: (params: DocumentQuery = {}) =>
    request<DocumentRecord[]>(`/documents${query({ ...params })}`),
  getDocument: (id: string) => request<DocumentRecord>(`/documents/${id}`),
  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),
  documentFileUrl: (id: string) => `${API_BASE_URL}/documents/${id}/file`,
  documentStatus: (id: string) => request<DocumentStatus>(`/documents/${id}/status`),
  processDocument: (id: string, force = false) =>
    request<DocumentRecord>(`/documents/${id}/process`, json("POST", { force })),
  retryDocument: (id: string) => request<DocumentRecord>(`/documents/${id}/retry`, { method: "POST" }),
  setLanguageOverride: (id: string, language: string | null) =>
    request<DocumentRecord>(`/documents/${id}`, json("PATCH", { language_override: language })),
  summarizeDocument: (id: string, responseLanguage: string) =>
    request<AnswerResponse>(`/documents/${id}/summary`, json("POST", { response_language: responseLanguage })),
  getChunk: (documentId: string, chunkId: string) => request<Chunk>(`/documents/${documentId}/chunks/${chunkId}`),

  listConversations: (workspaceId?: string) =>
    request<Conversation[]>(`/conversations${query({ workspace_id: workspaceId })}`),
  createConversation: (workspaceId: string, title?: string) =>
    request<Conversation>("/chat/conversations", json("POST", { workspace_id: workspaceId, title })),
  getConversation: (id: string) => request<ConversationDetail>(`/chat/conversations/${id}`),
  deleteConversation: (id: string) => request<void>(`/chat/conversations/${id}`, { method: "DELETE" }),
  startConversation: (workspaceId: string, payload: MessageCreate) =>
    request<MessageExchange>("/chat/messages", json("POST", { ...payload, workspace_id: workspaceId })),
  sendMessage: (conversationId: string, payload: MessageCreate) =>
    request<MessageExchange>(`/chat/conversations/${conversationId}/messages`, json("POST", payload)),

  /** One cited answer that is not saved as a conversation. */
  query: (payload: QueryRequest) => request<AnswerResponse>("/chat/query", json("POST", payload)),
  analyzeFir: (payload: FirAnalyzeRequest) => request<FirAnalysis>("/fir/analyze", json("POST", payload)),
};

export interface UploadHandle {
  promise: Promise<DocumentRecord>;
  abort: () => void;
}

/** Upload a PDF with progress reporting (fetch has no upload progress events). */
export function uploadDocument(
  workspaceId: string,
  file: File,
  onProgress?: (fraction: number) => void,
): UploadHandle {
  const xhr = new XMLHttpRequest();
  const promise = new Promise<DocumentRecord>((resolve, reject) => {
    const form = new FormData();
    form.append("workspace_id", workspaceId);
    form.append("file", file, file.name);

    xhr.open("POST", `${API_BASE_URL}/documents/upload`);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded / event.total);
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON body */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as DocumentRecord);
      else reject(toApiError(xhr.status, body));
    };
    xhr.onerror = () => reject(new ApiError(NETWORK_MESSAGE, 0, "network_error"));
    xhr.onabort = () => reject(new ApiError("Upload cancelled.", 0, "aborted"));
    xhr.send(form);
  });
  return { promise, abort: () => xhr.abort() };
}
