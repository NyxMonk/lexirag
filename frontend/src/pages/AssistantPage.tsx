import { AlertTriangle, ArrowUp, Check, ChevronDown, Info, Loader2, MessageSquareText, Plus, RotateCw, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { LanguageSelect } from "@/components/LanguageSelect";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/misc";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AssistantMessage } from "@/features/assistant/AnswerView";
import {
  useConversation,
  useConversations,
  useDeleteConversation,
  useDocuments,
  useSendMessage,
  useSystemInfo,
  useWorkspaces,
} from "@/hooks/queries";
import { usePreferences } from "@/hooks/usePreferences";
import { useToast } from "@/hooks/useToast";
import { LANGUAGES } from "@/lib/languages";
import { cn, formatRelative } from "@/lib/utils";
import type { ResponseLanguage } from "@/types/api";

const EXAMPLES = [
  { doc: "English", ask: "हिन्दी", answer: "Hindi" },
  { doc: "हिन्दी", ask: "English", answer: "English" },
  { doc: "বাংলা", ask: "मराठी", answer: "Marathi" },
  { doc: "English", ask: "Français", answer: "French" },
];

export function AssistantPage() {
  const [params, setParams] = useSearchParams();
  const workspaces = useWorkspaces();
  const info = useSystemInfo();
  const { preferences } = usePreferences();
  const { toast } = useToast();

  const workspaceId = params.get("workspace") ?? "";
  const conversationId = params.get("conversation");
  const [selectedDocs, setSelectedDocs] = useState<string[]>([]);
  const [responseLanguage, setResponseLanguage] = useState<ResponseLanguage>(preferences.responseLanguage);
  const [draft, setDraft] = useState("");
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);

  const conversations = useConversations(workspaceId || undefined);
  const conversation = useConversation(conversationId);
  const documents = useDocuments({ workspace_id: workspaceId }, Boolean(workspaceId));
  const deleteConversation = useDeleteConversation();
  const send = useSendMessage();
  const endRef = useRef<HTMLDivElement>(null);

  const readyDocs = useMemo(
    () => (documents.data ?? []).filter((d) => d.processing_status === "completed"),
    [documents.data],
  );
  const noWorkspaces = workspaces.data?.length === 0;

  useEffect(() => {
    if (!workspaceId && workspaces.data?.length) {
      setParams({ workspace: workspaces.data[0].id }, { replace: true });
    }
  }, [workspaceId, workspaces.data, setParams]);

  useEffect(() => setSelectedDocs([]), [workspaceId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [conversation.data?.messages.length, pendingQuestion]);

  // What blocks answering, in the order a user needs to fix it.
  const blocker = !info.data
    ? null
    : !info.data.retrieval_engine_available
      ? "The embedding model is not downloaded. Run `python -m app.cli download-models` in the backend folder, then restart."
      : !info.data.model_provider.configured
        ? "No answer provider is configured. Set LLM_PROVIDER (ollama, anthropic or gemini) and its credentials in .env, then restart the backend."
        : workspaceId && documents.data && readyDocs.length === 0
          ? "No documents in this workspace are ready yet. Upload a PDF and wait until it shows Ready."
          : null;
  const canSend = Boolean(workspaceId) && !blocker && !send.isPending && draft.trim().length > 0;

  function selectConversation(id: string | null) {
    const next: Record<string, string> = { workspace: workspaceId };
    if (id) next.conversation = id;
    setParams(next);
    send.reset();
    setPendingQuestion(null);
  }

  async function submit(text = draft) {
    const question = text.trim();
    if (!question || !workspaceId || blocker) return;
    setPendingQuestion(question);
    setDraft("");
    try {
      const payload = {
        content: question,
        document_ids: selectedDocs.length ? selectedDocs : null,
        response_language: responseLanguage,
      };
      // A new conversation is created by the server only when the first answer succeeds.
      const exchange = await send.mutateAsync({ id: conversationId, workspaceId, payload });
      if (!conversationId) setParams({ workspace: workspaceId, conversation: exchange.conversation_id }, { replace: true });
      setPendingQuestion(null);
    } catch {
      setDraft(question); // keep the question so it can be retried
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSend) void submit();
    }
  }

  async function removeConversation(id: string) {
    try {
      await deleteConversation.mutateAsync(id);
      if (id === conversationId) selectConversation(null);
    } catch (err) {
      toast({ title: "Could not delete conversation", description: (err as Error).message, tone: "error" });
    }
  }

  const messages = conversation.data?.messages ?? [];
  const visibleConversations = (conversations.data ?? []).filter((c) => c.message_count > 0 || c.id === conversationId);
  const showIntro = !conversationId && !pendingQuestion;

  return (
    <div className="flex h-full">
      {/* Conversation sidebar */}
      <aside className="flex w-[264px] shrink-0 flex-col border-r bg-surface">
        <div className="flex h-14 items-center justify-between border-b px-4">
          <p className="text-[13px] font-semibold">Conversations</p>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => selectConversation(null)}
            disabled={!workspaceId}
            title="New conversation"
            aria-label="New conversation"
          >
            <Plus />
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {conversations.isLoading ? (
            <div className="space-y-2 p-2">
              <Skeleton className="h-8" />
              <Skeleton className="h-8" />
            </div>
          ) : conversations.isError ? (
            <ErrorState error={conversations.error} onRetry={() => conversations.refetch()} className="m-1" />
          ) : visibleConversations.length === 0 ? (
            <p className="px-3 py-6 text-center text-[12.5px] leading-relaxed text-muted-foreground">
              Questions you ask in this workspace are saved here.
            </p>
          ) : (
            visibleConversations.map((c) => (
              <div
                key={c.id}
                className={cn(
                  "group flex items-center rounded-md transition-colors",
                  c.id === conversationId ? "bg-accent" : "hover:bg-accent/60",
                )}
              >
                <button onClick={() => selectConversation(c.id)} className="flex min-w-0 flex-1 flex-col px-3 py-2 text-left">
                  <span className="truncate text-[13px] font-medium">{c.title}</span>
                  <span className="text-[11.5px] text-muted-foreground">{formatRelative(c.updated_at)}</span>
                </button>
                <button
                  onClick={() => removeConversation(c.id)}
                  aria-label={`Delete conversation ${c.title}`}
                  className="mr-1.5 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))
          )}
        </div>
      </aside>

      {/* Conversation area */}
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex h-14 shrink-0 items-center gap-4 border-b bg-surface px-5">
          <div className="flex items-center gap-2">
            <Label htmlFor="as-ws" className="label-caps">
              Workspace
            </Label>
            <Select
              value={workspaceId}
              onValueChange={(v) => setParams({ workspace: v })}
              disabled={!workspaces.data?.length}
            >
              <SelectTrigger id="as-ws" className="h-8 w-44">
                <SelectValue placeholder={noWorkspaces ? "No workspaces" : "Select…"} />
              </SelectTrigger>
              <SelectContent>
                {workspaces.data?.map((w) => (
                  <SelectItem key={w.id} value={w.id}>
                    {w.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <Label htmlFor="as-doc" className="label-caps">
              Scope
            </Label>
            <DropdownMenu>
              <DropdownMenuTrigger asChild disabled={!workspaceId}>
                <button
                  id="as-doc"
                  className="flex h-8 w-52 items-center justify-between gap-2 rounded-md border border-input bg-surface px-3 text-sm shadow-subtle transition-colors hover:border-foreground/20 disabled:opacity-50"
                >
                  <span className="truncate">
                    {selectedDocs.length === 0
                      ? `All ready documents (${readyDocs.length})`
                      : selectedDocs.length === 1
                        ? readyDocs.find((d) => d.id === selectedDocs[0])?.original_filename ?? "1 document"
                        : `${selectedDocs.length} documents`}
                  </span>
                  <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-50" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-72">
                <DropdownMenuItem onSelect={() => setSelectedDocs([])}>
                  <Check className={cn(selectedDocs.length ? "opacity-0" : "opacity-100")} />
                  Entire workspace
                </DropdownMenuItem>
                {(documents.data?.length ?? 0) > 0 && <DropdownMenuSeparator />}
                {documents.data?.map((d) => {
                  const ready = d.processing_status === "completed";
                  const on = selectedDocs.includes(d.id);
                  return (
                    <DropdownMenuItem
                      key={d.id}
                      disabled={!ready}
                      onSelect={(e) => {
                        e.preventDefault(); // keep the menu open for multi-select
                        setSelectedDocs((cur) => (on ? cur.filter((x) => x !== d.id) : [...cur, d.id]));
                      }}
                    >
                      <Check className={cn(on ? "opacity-100" : "opacity-0")} />
                      <span className="truncate">{d.original_filename}</span>
                      {!ready && <span className="ml-auto text-[11px] text-muted-foreground">not ready</span>}
                    </DropdownMenuItem>
                  );
                })}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Label htmlFor="as-lang" className="label-caps">
              Answer in
            </Label>
            <LanguageSelect
              id="as-lang"
              className="h-8 w-44"
              value={responseLanguage}
              onValueChange={(v) => setResponseLanguage(v as ResponseLanguage)}
              extraOption={{ value: "match", label: "Language of question" }}
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {noWorkspaces ? (
            <div className="mx-auto max-w-xl px-6 py-20">
              <EmptyState
                icon={MessageSquareText}
                title="No workspace to ask about"
                description="Create a workspace and upload documents first."
              />
            </div>
          ) : showIntro ? (
            <div className="mx-auto max-w-2xl px-6 pb-10 pt-20 text-center">
              <p className="label-caps">Assistant</p>
              <h1 className="display mt-3 text-[34px] leading-tight">Ask in one language. Read in another.</h1>
              <p className="mx-auto mt-3 max-w-lg text-[14px] leading-relaxed text-muted-foreground">
                The document language, the question language and the answer language are independent. Every answer
                cites the original passages and pages it relies on.
              </p>
              <div className="mx-auto mt-10 grid max-w-xl grid-cols-2 gap-2.5 text-left">
                {EXAMPLES.map((ex) => (
                  <div key={ex.doc + ex.ask} className="rounded-lg border bg-card px-4 py-3 shadow-subtle">
                    <div className="grid grid-cols-3 gap-2 text-[11px]">
                      <span className="label-caps">Document</span>
                      <span className="label-caps">Question</span>
                      <span className="label-caps">Answer</span>
                    </div>
                    <div className="mt-1 grid grid-cols-3 gap-2 font-serif text-[16px]">
                      <span>{ex.doc}</span>
                      <span>{ex.ask}</span>
                      <span>{LANGUAGES.find((l) => l.name === ex.answer)?.nativeName}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-8 px-6 py-8">
              {conversation.isLoading && <Skeleton className="h-40" />}
              {conversation.isError && (
                <ErrorState error={conversation.error} onRetry={() => conversation.refetch()} />
              )}
              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="flex justify-end">
                    <p
                      lang={m.language ?? undefined}
                      className="max-w-[85%] whitespace-pre-line rounded-xl bg-accent px-4 py-2.5 text-[14.5px]"
                    >
                      {m.content}
                    </p>
                  </div>
                ) : (
                  <AssistantMessage key={m.id} message={m} />
                ),
              )}
              {pendingQuestion && (
                <>
                  <div className="flex justify-end">
                    <p className="max-w-[85%] whitespace-pre-line rounded-xl bg-accent px-4 py-2.5 text-[14.5px]">
                      {pendingQuestion}
                    </p>
                  </div>
                  {send.isPending ? (
                    <div className="flex items-center gap-2 text-[13px] text-muted-foreground" role="status">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Searching the documents and drafting a cited answer…
                    </div>
                  ) : send.isError ? (
                    <div role="alert" className="flex items-start gap-3 rounded-lg border border-destructive/25 bg-destructive/[0.04] px-4 py-3">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                      <div className="min-w-0 flex-1 text-sm">
                        <p className="font-medium">The question could not be answered</p>
                        <p className="mt-0.5 text-muted-foreground">
                          {send.error?.message}
                        </p>
                      </div>
                      <Button variant="outline" size="sm" onClick={() => submit(pendingQuestion)}>
                        <RotateCw /> Retry
                      </Button>
                    </div>
                  ) : null}
                </>
              )}
              <div ref={endRef} />
            </div>
          )}
        </div>

        {/* Composer */}
        <div className="shrink-0 border-t bg-surface px-6 py-4">
          <div className="mx-auto max-w-3xl">
            {blocker && (
              <div className="mb-3 flex items-start gap-2.5 rounded-md border bg-muted/50 px-3.5 py-2.5 text-[12.5px] text-muted-foreground">
                <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{blocker}</span>
              </div>
            )}
            <div
              className={cn(
                "flex items-end gap-2 rounded-xl border bg-background p-2 shadow-subtle transition-colors",
                !blocker && "focus-within:border-foreground/30",
              )}
            >
              <Textarea
                aria-label="Message"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={onKeyDown}
                disabled={Boolean(blocker) || !workspaceId}
                rows={2}
                maxLength={2000}
                placeholder={blocker ? "Answering is not available yet" : "Ask about these documents in any supported language…"}
                className="min-h-[52px] border-0 bg-transparent shadow-none focus-visible:ring-0"
              />
              <Button
                size="icon"
                className="h-9 w-9 shrink-0 rounded-lg"
                disabled={!canSend}
                onClick={() => submit()}
                aria-label="Send"
              >
                {send.isPending ? <Loader2 className="animate-spin" /> : <ArrowUp />}
              </Button>
            </div>
            <p className="mt-2 text-center text-[11px] text-muted-foreground">
              Answers come only from your documents and cite their pages. They are not legal advice.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
