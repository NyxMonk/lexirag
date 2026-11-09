import { describe, expect, it } from "vitest";

import { languageLabel, LANGUAGES } from "@/lib/languages";
import { formatBytes, formatRelative, pluralize } from "@/lib/utils";

describe("formatBytes", () => {
  it("formats sizes with sensible precision", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(50 * 1024 * 1024)).toBe("50 MB");
    expect(formatBytes(-1)).toBe("—");
  });
});

describe("formatRelative", () => {
  it("describes recent times", () => {
    const now = new Date("2026-11-02T12:00:00Z");
    expect(formatRelative("2026-11-02T11:59:50Z", now)).toBe("just now");
    expect(formatRelative("2026-11-02T11:30:00Z", now)).toBe("30 min ago");
    expect(formatRelative("2026-11-01T12:00:00Z", now)).toBe("1 d ago");
  });
});

describe("languages", () => {
  it("supports the six launch languages with Gurmukhi Punjabi", () => {
    expect(LANGUAGES.map((l) => l.code)).toEqual(["en", "hi", "bn", "mr", "pa", "fr"]);
    expect(LANGUAGES.find((l) => l.code === "pa")?.script).toBe("Gurmukhi");
    expect(languageLabel("hi")).toBe("Hindi · हिन्दी");
    expect(languageLabel(null)).toBe("Not detected");
  });

  it("pluralizes", () => {
    expect(pluralize(1, "document")).toBe("1 document");
    expect(pluralize(3, "document")).toBe("3 documents");
  });
});
