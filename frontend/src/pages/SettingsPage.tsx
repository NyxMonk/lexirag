import { Check, KeyRound, Monitor, Moon, Sun, X } from "lucide-react";
import type { ReactNode } from "react";

import { LanguageSelect } from "@/components/LanguageSelect";
import { Page, PageHeader } from "@/components/layout/Page";
import { Button } from "@/components/ui/button";
import { Card, Skeleton } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { useHealth, useModels, useSystemInfo } from "@/hooks/queries";
import { usePreferences, type Preferences, type Theme } from "@/hooks/usePreferences";
import { useToast } from "@/hooks/useToast";
import type { LanguageCode } from "@/lib/languages";
import { API_BASE_URL } from "@/lib/config";
import { cn, formatBytes } from "@/lib/utils";

function Section({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <section className="grid grid-cols-[260px_1fr] gap-10 border-b py-9 first:pt-0 last:border-0">
      <div>
        <h2 className="text-[14px] font-semibold">{title}</h2>
        <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">{description}</p>
      </div>
      <Card className="divide-y">{children}</Card>
    </section>
  );
}

function Flag({ ok, yes, no }: { ok: boolean; yes: string; no: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px]">
      {ok ? <Check className="h-3.5 w-3.5" /> : <X className="h-3.5 w-3.5 text-muted-foreground" />}
      {ok ? yes : no}
    </span>
  );
}

function Row({ label, hint, htmlFor, children }: { label: string; hint?: ReactNode; htmlFor?: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6 px-5 py-4">
      <div className="min-w-0">
        <label htmlFor={htmlFor} className="text-[13.5px] font-medium">
          {label}
        </label>
        {hint && <p className="mt-0.5 text-[12.5px] text-muted-foreground">{hint}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

const THEMES: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

export function SettingsPage() {
  const { preferences, update, reset } = usePreferences();
  const info = useSystemInfo();
  const models = useModels();
  const health = useHealth();
  const { toast } = useToast();
  const generation = models.data?.generation;

  return (
    <Page className="max-w-[1000px]">
      <PageHeader eyebrow="Preferences" title="Settings" description="Preferences are saved in this browser." />

      <Section title="Language" description="Defaults for new conversations. Each can be changed per question.">
        <Row label="Interface language" hint="Interface translations are planned; English is used for now.">
          <LanguageSelect
            ariaLabel="Interface language"
            className="w-56"
            value={preferences.interfaceLanguage}
            onValueChange={(v) => update({ interfaceLanguage: v as LanguageCode })}
          />
        </Row>
        <Row label="Question language" hint="The language you usually ask in.">
          <LanguageSelect
            ariaLabel="Question language"
            className="w-56"
            value={preferences.queryLanguage}
            onValueChange={(v) => update({ queryLanguage: v as Preferences["queryLanguage"] })}
            extraOption={{ value: "auto", label: "Detect automatically" }}
          />
        </Row>
        <Row label="Response language" hint="The language answers are written in.">
          <LanguageSelect
            ariaLabel="Response language"
            className="w-56"
            value={preferences.responseLanguage}
            onValueChange={(v) => update({ responseLanguage: v as Preferences["responseLanguage"] })}
            extraOption={{ value: "match", label: "Language of question" }}
          />
        </Row>
      </Section>

      <Section
        title="Answer generation"
        description="Configured on the server in the .env file. Credentials never reach the browser."
      >
        {models.isLoading ? (
          <div className="p-5">
            <Skeleton className="h-16" />
          </div>
        ) : models.isError ? (
          <p className="px-5 py-4 text-[13px] text-destructive">Could not read server configuration.</p>
        ) : (
          <>
            <Row label="Provider" hint="LLM_PROVIDER: ollama, anthropic or gemini">
              {generation?.provider === "none" ? (
                <span className="text-[13.5px]">Not configured</span>
              ) : (
                <span className="text-[13.5px] capitalize">{generation?.provider}</span>
              )}
            </Row>
            <Row label="Model" hint="OLLAMA_MODEL, ANTHROPIC_MODEL or GEMINI_MODEL">
              <span className="font-mono text-[12.5px]">{generation?.model ?? "—"}</span>
            </Row>
            <Row label="Credentials" hint="API key or Ollama model present on the server">
              <Flag ok={Boolean(generation?.configured)} yes="Present" no="Not set" />
            </Row>
            <div className="flex items-start gap-2.5 px-5 py-4 text-[12.5px] leading-relaxed text-muted-foreground">
              <KeyRound className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              Edit the project&apos;s .env file and restart the backend to change the provider. Answers are generated
              only from retrieved passages and always cite them.
            </div>
          </>
        )}
      </Section>

      <Section title="Retrieval models" description="Run locally on this machine. Loaded on first use.">
        {models.data ? (
          <>
            {[
              ["Embeddings", models.data.embedding],
              ["Reranker", models.data.reranker],
            ].map(([label, m]) => {
              const model = m as typeof models.data.embedding;
              return (
                <Row key={label as string} label={label as string} hint={<span className="font-mono">{model.model}</span>}>
                  <span className="text-[13px]">
                    {!model.enabled
                      ? "Disabled"
                      : !model.downloaded
                        ? "Not downloaded"
                        : model.loaded
                          ? `Loaded on ${model.device?.toUpperCase()}`
                          : "Downloaded"}
                  </span>
                </Row>
              );
            })}
            <Row label="OCR (Tesseract)" hint={models.data.ocr.message ?? "Reads scanned pages"}>
              <Flag
                ok={models.data.ocr.available}
                yes={`Available · ${models.data.ocr.installed_languages.filter((l) => l !== "osd").join(", ")}`}
                no={models.data.ocr.enabled ? "Not installed" : "Disabled"}
              />
            </Row>
            <Row label="Retrieval" hint="Dense + BM25, fused with reciprocal rank fusion">
              <span className="text-[12.5px] tabular-nums text-muted-foreground">
                top {models.data.retrieval.final_top_k} of {models.data.retrieval.rerank_candidates} reranked · chunks ~
                {models.data.retrieval.chunk_target_tokens} tokens
              </span>
            </Row>
          </>
        ) : (
          <div className="p-5">
            <Skeleton className="h-16" />
          </div>
        )}
      </Section>

      <Section title="Application" description="Appearance and behaviour.">
        <Row label="Theme">
          <div className="inline-flex rounded-md border bg-muted/50 p-0.5" role="radiogroup" aria-label="Theme">
            {THEMES.map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                role="radio"
                aria-checked={preferences.theme === value}
                onClick={() => update({ theme: value })}
                className={cn(
                  "inline-flex h-7 items-center gap-1.5 rounded px-2.5 text-[12.5px] transition-colors",
                  preferences.theme === value
                    ? "bg-surface font-medium text-foreground shadow-subtle"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                <Icon className="h-3.5 w-3.5" /> {label}
              </button>
            ))}
          </div>
        </Row>
        <Row label="Confirm before deleting" hint="Ask before removing documents." htmlFor="pref-confirm">
          <Switch
            id="pref-confirm"
            checked={preferences.confirmBeforeDelete}
            onCheckedChange={(v) => update({ confirmBeforeDelete: v })}
          />
        </Row>
        <Row label="Citations panel" hint="Show the citations panel in the document viewer." htmlFor="pref-cite">
          <Switch
            id="pref-cite"
            checked={preferences.showCitationsPanel}
            onCheckedChange={(v) => update({ showCitationsPanel: v })}
          />
        </Row>
        <div className="flex justify-end px-5 py-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              reset();
              toast({ title: "Preferences reset" });
            }}
          >
            Reset to defaults
          </Button>
        </div>
      </Section>

      <Section title="About" description="Local installation details.">
        <Row label="Version">
          <span className="tabular-nums text-[13px]">{info.data?.version ?? "—"}</span>
        </Row>
        <Row label="API endpoint">
          <span className="font-mono text-[12.5px]">{API_BASE_URL}</span>
        </Row>
        <Row label="Database">
          <span className="text-[13px]">
            {health.data?.database.status === "ok"
              ? `Connected · pgvector ${health.data.database.pgvector_version ?? "missing"}`
              : health.isLoading
                ? "Checking…"
                : "Unavailable"}
          </span>
        </Row>
        <Row label="Upload limit">
          <span className="text-[13px] tabular-nums">{info.data ? formatBytes(info.data.max_upload_size_bytes) : "—"}</span>
        </Row>
      </Section>
    </Page>
  );
}

