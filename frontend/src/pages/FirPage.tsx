import { AlertTriangle, FileSearch, Info, Loader2, Scale, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { LanguageSelect } from "@/components/LanguageSelect";
import { Page, PageHeader, SectionHeader } from "@/components/layout/Page";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/misc";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { AssistantMessage } from "@/features/assistant/AnswerView";
import { FIR_SAMPLES } from "@/features/fir/samples";
import { useAnalyzeFir, useDocuments, useQueryAnswer, useSystemInfo, useWorkspaces } from "@/hooks/queries";
import { usePreferences } from "@/hooks/usePreferences";
import { cn } from "@/lib/utils";
import type { FirAnalysis, FirCharge, FirClassification, ResponseLanguage } from "@/types/api";

const CODE_NAMES: Record<string, string> = {
  IPC: "Indian Penal Code, 1860",
  BNS: "Bharatiya Nyaya Sanhita, 2023",
};

const DATE_SOURCE: Record<FirAnalysis["offence_date_source"], string> = {
  provided: "entered by you",
  occurrence: "date of occurrence in the FIR",
  earliest: "earliest date in the FIR (no occurrence label found)",
  none: "not found",
};

function formatDate(iso: string) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

function Classification({ value, label }: { value: FirClassification | null; label: string }) {
  if (!value) return null;
  const strong = value === "non-bailable" || value === "cognizable";
  return (
    <span
      title={label}
      className={cn(
        "inline-flex h-[22px] items-center rounded-full border px-2.5 text-[11.5px] font-medium capitalize",
        strong ? "border-foreground bg-foreground text-background" : "bg-surface text-foreground",
        value === "depends" && "border-dashed text-muted-foreground",
      )}
    >
      {value === "depends" ? `${label}: depends` : value}
    </span>
  );
}

function ChargeRow({ charge }: { charge: FirCharge }) {
  const known = charge.code === "IPC" || charge.code === "BNS";
  return (
    <div className="grid grid-cols-[120px_1fr] gap-5 border-b px-5 py-4 last:border-b-0">
      <div>
        <p className="font-serif text-[22px] leading-none">§ {charge.section}</p>
        <p className="mt-1.5 text-[11.5px] text-muted-foreground">
          {charge.code ?? "Code unknown"}
          {charge.code_source === "offence_date" && " · by date"}
        </p>
      </div>
      <div className="min-w-0">
        {charge.in_reference ? (
          <>
            <p className="text-[14.5px] font-medium leading-snug">{charge.title}</p>
            {charge.reference_section && charge.reference_section !== charge.section && (
              <p className="mt-0.5 text-[12px] text-muted-foreground">Closest listed provision: § {charge.reference_section}</p>
            )}
            {charge.kind === "liability" ? (
              <p className="mt-2 text-[13px] text-muted-foreground">{charge.note}</p>
            ) : (
              <>
                <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                  <Classification value={charge.cognizable} label="Cognizable" />
                  <Classification value={charge.bailable} label="Bailable" />
                  {charge.court && (
                    <span className="inline-flex h-[22px] items-center rounded-full border bg-surface px-2.5 text-[11.5px]">
                      Triable by: {charge.court}
                    </span>
                  )}
                </div>
                <dl className="mt-3 grid grid-cols-[110px_1fr] gap-x-3 gap-y-1.5 text-[13px]">
                  <dt className="text-muted-foreground">Punishment</dt>
                  <dd>{charge.punishment}</dd>
                  {charge.note && (
                    <>
                      <dt className="text-muted-foreground">Note</dt>
                      <dd>{charge.note}</dd>
                    </>
                  )}
                </dl>
              </>
            )}
            {charge.corresponds_to.length > 0 && (
              <p className="mt-2.5 text-[12.5px] text-muted-foreground">
                <span className="label-caps mr-1.5">{charge.code === "IPC" ? "Now under BNS" : "Formerly IPC"}</span>
                {charge.corresponds_to.map((c) => `§ ${c.section}${c.title ? ` (${c.title})` : ""}`).join("; ")}
                <span className="ml-1.5 italic">— unofficial correspondence</span>
              </p>
            )}
          </>
        ) : (
          <p className="text-[13.5px] text-muted-foreground">
            {charge.code_source === "other_act"
              ? `A provision of the ${charge.code}. Only IPC and BNS offences are covered by the reference table.`
              : known
                ? `Section ${charge.section} of the ${charge.code} is not in the reference table yet.`
                : "The FIR does not say which code this section belongs to, and no offence date was found."}
          </p>
        )}
      </div>
    </div>
  );
}

function explainQuestion(analysis: FirAnalysis): string | null {
  const items = analysis.charges.filter((c) => c.in_reference && c.kind === "offence");
  if (items.length === 0) return null;
  const byCode = new Map<string, string[]>();
  for (const c of items) {
    const list = byCode.get(c.code!) ?? [];
    list.push(`section ${c.section} (${c.title})`);
    byCode.set(c.code!, list);
  }
  const parts = [...byCode.entries()].map(([code, list]) => `${CODE_NAMES[code] ?? code}: ${list.join("; ")}`);
  return (
    "Explain in plain language, for a person named in or affected by an FIR, what each of these offences means " +
    `and what has to be shown for it to apply. ${parts.join(". ")}. ` +
    "State punishments only as written in the sources."
  );
}

export function FirPage() {
  const [params, setParams] = useSearchParams();
  const workspaces = useWorkspaces();
  const info = useSystemInfo();
  const { preferences } = usePreferences();
  const workspaceId = params.get("workspace") ?? "";
  const documents = useDocuments({ workspace_id: workspaceId }, Boolean(workspaceId));

  const [mode, setMode] = useState<"document" | "text">("text");
  const [documentId, setDocumentId] = useState("");
  const [text, setText] = useState("");
  const [sampleId, setSampleId] = useState<string | null>(null);
  const [offenceDate, setOffenceDate] = useState("");
  const [language, setLanguage] = useState<string>(preferences.responseLanguage === "match" ? "en" : preferences.responseLanguage);

  const analyze = useAnalyzeFir();
  const explain = useQueryAnswer();

  const readyDocs = useMemo(
    () => (documents.data ?? []).filter((d) => d.processing_status === "completed"),
    [documents.data],
  );

  useEffect(() => {
    if (!workspaceId && workspaces.data?.length) setParams({ workspace: workspaces.data[0].id }, { replace: true });
  }, [workspaceId, workspaces.data, setParams]);
  useEffect(() => setDocumentId(""), [workspaceId]);

  const canAnalyze = mode === "document" ? Boolean(documentId) : text.trim().length > 0;
  const analysis = analyze.data;

  function run(dateOverride = offenceDate) {
    explain.reset();
    analyze.mutate(
      mode === "document"
        ? { document_id: documentId, workspace_id: workspaceId || null, offence_date: dateOverride || null }
        : { text, offence_date: dateOverride || null },
    );
  }

  const question = analysis ? explainQuestion(analysis) : null;
  // Explanations come from the workspace's documents (e.g. the IPC or BNS Act); the FIR itself is left out.
  const explainDocs = readyDocs.filter((d) => d.id !== analysis?.source.document_id);
  const explainBlocker = !info.data
    ? null
    : !info.data.answering_available
      ? "A cited explanation needs an answer provider and the embedding model (see Settings). The charge card above works without them."
      : !workspaceId
        ? "Select a workspace that contains the Indian Penal Code or Bharatiya Nyaya Sanhita to get a cited explanation."
        : explainDocs.length === 0
          ? "Upload the Indian Penal Code or Bharatiya Nyaya Sanhita PDF to this workspace to get a cited explanation."
          : !question
            ? "None of the sections were found in the reference table, so there is nothing to explain yet."
            : null;

  function runExplain() {
    if (!question || !workspaceId) return;
    explain.mutate({
      workspace_id: workspaceId,
      question,
      document_ids: explainDocs.map((d) => d.id),
      response_language: language as ResponseLanguage,
    });
  }

  return (
    <Page>
      <PageHeader
        eyebrow="Tools"
        title="FIR explainer"
        description="Find the sections in a First Information Report, see which code applies on the offence date, and read what each charge means: bailable or not, cognizable or not, punishment and court."
      />

      <Card className="p-5">
        <div className="flex flex-wrap items-center gap-4">
          <div className="inline-flex rounded-md border bg-muted/40 p-0.5" role="tablist" aria-label="FIR source">
            {(["text", "document"] as const).map((m) => (
              <button
                key={m}
                role="tab"
                aria-selected={mode === m}
                onClick={() => setMode(m)}
                className={cn(
                  "h-7 rounded px-3 text-[13px] transition-colors",
                  mode === m ? "bg-surface font-medium shadow-subtle" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {m === "text" ? "Paste text" : "From a document"}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <Label htmlFor="fir-ws" className="label-caps">
              Workspace
            </Label>
            <Select value={workspaceId} onValueChange={(v) => setParams({ workspace: v })} disabled={!workspaces.data?.length}>
              <SelectTrigger id="fir-ws" className="h-8 w-48">
                <SelectValue placeholder={workspaces.data?.length === 0 ? "No workspaces" : "Select…"} />
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
        </div>

        {mode === "document" ? (
          <div className="mt-4 flex items-center gap-2">
            <Label htmlFor="fir-doc" className="label-caps">
              FIR document
            </Label>
            <Select value={documentId} onValueChange={setDocumentId} disabled={readyDocs.length === 0}>
              <SelectTrigger id="fir-doc" className="h-8 w-80">
                <SelectValue placeholder={readyDocs.length ? "Select a processed document…" : "No processed documents"} />
              </SelectTrigger>
              <SelectContent>
                {readyDocs.map((d) => (
                  <SelectItem key={d.id} value={d.id}>
                    {d.original_filename}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : (
          <div className="mt-4">
            <div className="mb-2 flex flex-wrap items-center gap-1.5">
              <span className="label-caps mr-1">Synthetic samples</span>
              {FIR_SAMPLES.map((s) => (
                <Button
                  key={s.id}
                  size="sm"
                  variant={sampleId === s.id ? "secondary" : "outline"}
                  className="h-7 text-[12px]"
                  onClick={() => {
                    setText(s.text);
                    setSampleId(s.id);
                  }}
                >
                  {s.label}
                </Button>
              ))}
            </div>
            <Textarea
              aria-label="FIR text"
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setSampleId(null);
              }}
              rows={7}
              maxLength={50000}
              placeholder="Paste the FIR text, or at least the 'Acts and sections' line and the date of occurrence…"
            />
            {sampleId && (
              <p className="mt-1.5 text-[11.5px] text-muted-foreground">
                Synthetic sample: invented names and facts, for demonstration only.
              </p>
            )}
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-end gap-3">
          <div>
            <Label htmlFor="fir-date" className="label-caps">
              Offence date (optional)
            </Label>
            <Input
              id="fir-date"
              type="date"
              className="mt-1 h-8 w-44"
              value={offenceDate}
              onChange={(e) => setOffenceDate(e.target.value)}
            />
          </div>
          <Button onClick={() => run()} disabled={!canAnalyze || analyze.isPending}>
            {analyze.isPending ? <Loader2 className="animate-spin" /> : <FileSearch />}
            Analyse FIR
          </Button>
        </div>
      </Card>

      {analyze.isError && (
        <div role="alert" className="mt-6 flex items-start gap-3 rounded-lg border border-destructive/25 bg-destructive/[0.04] px-4 py-3 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          {analyze.error.message}
        </div>
      )}

      {analysis && (
        <div className="mt-8 space-y-8">
          <section>
            <SectionHeader title="Applicable law" />
            <Card className="grid grid-cols-1 divide-y sm:grid-cols-3 sm:divide-x sm:divide-y-0">
              <div className="px-5 py-4">
                <p className="label-caps">Offence date</p>
                <p className="mt-1.5 font-serif text-[20px]">{analysis.offence_date ? formatDate(analysis.offence_date) : "—"}</p>
                <p className="mt-0.5 text-[12px] text-muted-foreground">{DATE_SOURCE[analysis.offence_date_source]}</p>
              </div>
              <div className="px-5 py-4">
                <p className="label-caps">Code in force</p>
                <p className="mt-1.5 font-serif text-[20px]">
                  {analysis.applicable_code ? CODE_NAMES[analysis.applicable_code] : "Unknown"}
                </p>
                <p className="mt-0.5 text-[12px] text-muted-foreground">
                  BNS applies to offences from {formatDate(analysis.bns_commencement)}
                </p>
              </div>
              <div className="px-5 py-4">
                <p className="label-caps">Sections found</p>
                <p className="mt-1.5 font-serif text-[20px]">{analysis.charges.length}</p>
                <p className="mt-0.5 text-[12px] text-muted-foreground">
                  {analysis.charges.filter((c) => c.bailable === "non-bailable").length} non-bailable ·{" "}
                  {analysis.charges.filter((c) => c.cognizable === "cognizable").length} cognizable
                </p>
              </div>
            </Card>
            {analysis.date_candidates.length > 1 && (
              <p className="mt-2 text-[12px] text-muted-foreground">
                Dates in the FIR:{" "}
                {analysis.date_candidates.map((d, i) => (
                  <button
                    key={`${d.date}-${i}`}
                    className="mr-2 underline decoration-dotted underline-offset-2 hover:text-foreground"
                    title="Use this as the offence date"
                    onClick={() => {
                      setOffenceDate(d.date);
                      run(d.date);
                    }}
                  >
                    {formatDate(d.date)} ({d.kind})
                  </button>
                ))}
              </p>
            )}
          </section>

          {analysis.warnings.length > 0 && (
            <div className="space-y-1.5">
              {analysis.warnings.map((w) => (
                <p key={w} className="flex items-start gap-2 rounded-md border bg-muted/50 px-3.5 py-2.5 text-[12.5px] text-muted-foreground">
                  <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  {w}
                </p>
              ))}
            </div>
          )}

          {analysis.charges.length > 0 && (
            <section>
              <SectionHeader title="Charge card" />
              <Card>
                {analysis.charges.map((c) => (
                  <ChargeRow key={`${c.code}-${c.section}`} charge={c} />
                ))}
              </Card>
              {!analysis.reference.validated && (
                <div className="mt-3 rounded-md border border-dashed px-4 py-3 text-[12px] text-muted-foreground">
                  <p className="font-medium text-foreground">Reference data, not yet verified</p>
                  <ul className="mt-1 list-disc space-y-0.5 pl-4">
                    {analysis.reference.caveats.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                  <p className="mt-1.5">Sources: {analysis.reference.sources.join("; ")}.</p>
                </div>
              )}
            </section>
          )}

          <section>
            <SectionHeader
              title="Plain-language explanation"
              action={
                <div className="flex items-center gap-2">
                  <LanguageSelect ariaLabel="Explanation language" className="h-8 w-44" value={language} onValueChange={setLanguage} />
                  <Button size="sm" onClick={runExplain} disabled={Boolean(explainBlocker) || explain.isPending}>
                    {explain.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
                    Explain with citations
                  </Button>
                </div>
              }
            />
            {explainBlocker && (
              <p className="flex items-start gap-2 rounded-md border bg-muted/50 px-3.5 py-2.5 text-[12.5px] text-muted-foreground">
                <Scale className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                {explainBlocker}
              </p>
            )}
            {explain.isPending && (
              <p className="text-[13px] text-muted-foreground" role="status">
                Searching the Acts in this workspace and drafting a cited explanation…
              </p>
            )}
            {explain.isError && (
              <p role="alert" className="rounded-md border border-destructive/25 bg-destructive/[0.04] px-3 py-2 text-[12.5px]">
                {explain.error.message}
              </p>
            )}
            {explain.data && !explain.isPending && (
              <Card className="p-5">
                <AssistantMessage
                  message={{
                    id: "fir-explanation",
                    conversation_id: "",
                    role: "assistant",
                    content: explain.data.answer,
                    language: explain.data.language,
                    citations: explain.data.citations,
                    evidence_sufficient: explain.data.evidence_sufficient,
                    details: {
                      answer_source: explain.data.answer_source,
                      warnings: explain.data.warnings,
                      generation: explain.data.generation,
                    },
                    created_at: "",
                  }}
                />
              </Card>
            )}
          </section>

          <p className="border-t pt-4 text-center text-[11.5px] text-muted-foreground">{analysis.disclaimer}</p>
        </div>
      )}
    </Page>
  );
}
