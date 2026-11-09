export type LanguageCode = "en" | "hi" | "bn" | "mr" | "pa" | "fr";

export interface LanguageOption {
  code: LanguageCode;
  name: string;
  nativeName: string;
  script: string;
}

// Kept in sync with backend/app/core/languages.py.
export const LANGUAGES: LanguageOption[] = [
  { code: "en", name: "English", nativeName: "English", script: "Latin" },
  { code: "hi", name: "Hindi", nativeName: "हिन्दी", script: "Devanagari" },
  { code: "bn", name: "Bengali", nativeName: "বাংলা", script: "Bengali" },
  { code: "mr", name: "Marathi", nativeName: "मराठी", script: "Devanagari" },
  { code: "pa", name: "Punjabi", nativeName: "ਪੰਜਾਬੀ", script: "Gurmukhi" },
  { code: "fr", name: "French", nativeName: "Français", script: "Latin" },
];

export function languageLabel(code: string | null | undefined): string {
  const lang = LANGUAGES.find((l) => l.code === code);
  if (!lang) return "Not detected";
  return lang.code === "en" ? lang.name : `${lang.name} · ${lang.nativeName}`;
}
