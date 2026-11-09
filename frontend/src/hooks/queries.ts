import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/services/api";
import {
  IN_PROGRESS_STATUSES,
  type DocumentQuery,
  type DocumentRecord,
  type MessageCreate,
  type WorkspaceCreate,
} from "@/types/api";

/** Poll every 2 s while any document in view is still being processed. */
const POLL_MS = 2000;
const isProcessing = (doc: DocumentRecord) => IN_PROGRESS_STATUSES.includes(doc.processing_status);

export const queryKeys = {
  health: ["health"] as const,
  systemInfo: ["system-info"] as const,
  workspaces: ["workspaces"] as const,
  workspace: (id: string) => ["workspaces", id] as const,
  documents: (params: DocumentQuery = {}) => ["documents", params] as const,
  document: (id: string) => ["document", id] as const,
  conversations: (workspaceId?: string) => ["conversations", workspaceId ?? "all"] as const,
  conversation: (id: string) => ["conversation", id] as const,
  models: ["models"] as const,
};

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: api.health,
    refetchInterval: 30_000,
    retry: false,
  });
}

export function useSystemInfo() {
  return useQuery({ queryKey: queryKeys.systemInfo, queryFn: api.systemInfo, staleTime: 60_000 });
}

export function useModels() {
  return useQuery({ queryKey: queryKeys.models, queryFn: api.models, refetchInterval: 15_000 });
}

export function useWorkspaces() {
  return useQuery({ queryKey: queryKeys.workspaces, queryFn: api.listWorkspaces });
}

export function useWorkspace(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.workspace(id ?? ""),
    queryFn: () => api.getWorkspace(id!),
    enabled: Boolean(id),
  });
}

export function useDocuments(params: DocumentQuery = {}, enabled = true) {
  return useQuery({
    queryKey: queryKeys.documents(params),
    queryFn: () => api.listDocuments(params),
    enabled,
    refetchInterval: (query) => (query.state.data?.some(isProcessing) ? POLL_MS : false),
  });
}

export function useDocument(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.document(id ?? ""),
    queryFn: () => api.getDocument(id!),
    enabled: Boolean(id),
    refetchInterval: (query) => (query.state.data && isProcessing(query.state.data) ? POLL_MS : false),
  });
}

export function useConversations(workspaceId?: string) {
  return useQuery({
    queryKey: queryKeys.conversations(workspaceId),
    queryFn: () => api.listConversations(workspaceId),
  });
}

/** Invalidate everything that summarises documents or workspaces. */
export function useInvalidateLibrary() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: ["workspaces"] }),
      client.invalidateQueries({ queryKey: ["documents"] }),
      client.invalidateQueries({ queryKey: ["document"] }),
      client.invalidateQueries({ queryKey: ["conversations"] }),
      client.invalidateQueries({ queryKey: ["system-info"] }),
    ]);
}

export function useCreateWorkspace() {
  const invalidate = useInvalidateLibrary();
  return useMutation({
    mutationFn: (data: WorkspaceCreate) => api.createWorkspace(data),
    onSuccess: () => invalidate(),
  });
}

export function useDeleteWorkspace() {
  const invalidate = useInvalidateLibrary();
  return useMutation({
    mutationFn: (id: string) => api.deleteWorkspace(id),
    onSuccess: () => invalidate(),
  });
}

export function useDeleteDocument() {
  const invalidate = useInvalidateLibrary();
  return useMutation({
    mutationFn: (id: string) => api.deleteDocument(id),
    onSuccess: () => invalidate(),
  });
}

export function useProcessDocument() {
  const invalidate = useInvalidateLibrary();
  return useMutation({
    mutationFn: ({ id, mode }: { id: string; mode: "process" | "reprocess" | "retry" }) =>
      mode === "retry" ? api.retryDocument(id) : api.processDocument(id, mode === "reprocess"),
    onSuccess: () => invalidate(),
  });
}

export function useSetLanguageOverride() {
  const invalidate = useInvalidateLibrary();
  return useMutation({
    mutationFn: ({ id, language }: { id: string; language: string | null }) => api.setLanguageOverride(id, language),
    onSuccess: () => invalidate(),
  });
}

export function useChunk(documentId: string | undefined, chunkId: string | null) {
  return useQuery({
    queryKey: ["chunk", documentId, chunkId],
    queryFn: () => api.getChunk(documentId!, chunkId!),
    enabled: Boolean(documentId && chunkId),
    staleTime: Infinity,
  });
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: queryKeys.conversation(id ?? ""),
    queryFn: () => api.getConversation(id!),
    enabled: Boolean(id),
  });
}

export function useCreateConversation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (workspaceId: string) => api.createConversation(workspaceId),
    onSuccess: () => client.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useDeleteConversation() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteConversation(id),
    onSuccess: () => client.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useSendMessage() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, workspaceId, payload }: { id: string | null; workspaceId: string; payload: MessageCreate }) =>
      id ? api.sendMessage(id, payload) : api.startConversation(workspaceId, payload),
    onSuccess: (data) =>
      Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.conversation(data.conversation_id) }),
        client.invalidateQueries({ queryKey: ["conversations"] }),
      ]),
  });
}

export function useSummarizeDocument() {
  return useMutation({
    mutationFn: ({ id, language }: { id: string; language: string }) => api.summarizeDocument(id, language),
  });
}
