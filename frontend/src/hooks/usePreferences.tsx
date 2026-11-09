import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import type { LanguageCode } from "@/lib/languages";

export type Theme = "system" | "light" | "dark";

export interface Preferences {
  interfaceLanguage: LanguageCode;
  /** "auto" means detect from the question text. */
  queryLanguage: LanguageCode | "auto";
  /** "match" means answer in the language the question was asked in. */
  responseLanguage: LanguageCode | "match";
  theme: Theme;
  confirmBeforeDelete: boolean;
  showCitationsPanel: boolean;
}

export const DEFAULT_PREFERENCES: Preferences = {
  interfaceLanguage: "en",
  queryLanguage: "auto",
  responseLanguage: "match",
  theme: "system",
  confirmBeforeDelete: true,
  showCitationsPanel: true,
};

const STORAGE_KEY = "lexirag.preferences";

function load(): Preferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...DEFAULT_PREFERENCES, ...(JSON.parse(raw) as Partial<Preferences>) };
  } catch {
    /* storage unavailable or corrupt; fall back to defaults */
  }
  return DEFAULT_PREFERENCES;
}

interface PreferencesContextValue {
  preferences: Preferences;
  update: (patch: Partial<Preferences>) => void;
  reset: () => void;
}

const PreferencesContext = createContext<PreferencesContextValue | null>(null);

function applyTheme(theme: Theme) {
  const dark =
    theme === "dark" ||
    (theme === "system" && typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState<Preferences>(load);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
    } catch {
      /* ignore */
    }
  }, [preferences]);

  useEffect(() => {
    applyTheme(preferences.theme);
    if (preferences.theme !== "system" || typeof matchMedia !== "function") return;
    const media = matchMedia("(prefers-color-scheme: dark)");
    const listener = () => applyTheme("system");
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, [preferences.theme]);

  const update = useCallback((patch: Partial<Preferences>) => {
    setPreferences((prev) => ({ ...prev, ...patch }));
  }, []);
  const reset = useCallback(() => setPreferences(DEFAULT_PREFERENCES), []);

  const value = useMemo(() => ({ preferences, update, reset }), [preferences, update, reset]);
  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences() {
  const ctx = useContext(PreferencesContext);
  if (!ctx) throw new Error("usePreferences must be used inside PreferencesProvider");
  return ctx;
}
