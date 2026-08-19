import { describe, expect, it } from "vitest";
import {
  BAND_STYLES,
  bandKeyFor,
  bandKeyForLabel,
  buildExport,
  countParagraphs,
  countWords,
  formatBytes,
  formatDate,
  messageForError,
} from "@/lib/format";
import { FALLBACK_CONFIG } from "@/lib/config";
import type { Analysis } from "@/lib/types";

const BANDS = FALLBACK_CONFIG.bands;

describe("countWords", () => {
  it.each([
    ["", 0],
    ["   ", 0],
    ["one", 1],
    ["one two three", 3],
    ["  spaced   out  words ", 3],
    ["line one\nline two", 4],
  ])("counts %j as %i", (input, expected) => {
    expect(countWords(input)).toBe(expected);
  });
});

describe("countParagraphs", () => {
  it("splits on blank lines", () => {
    expect(countParagraphs("one\n\ntwo\n\nthree")).toBe(3);
  });

  it("ignores single newlines", () => {
    expect(countParagraphs("line one\nline two")).toBe(1);
  });

  it("ignores whitespace-only paragraphs", () => {
    expect(countParagraphs("one\n\n   \n\ntwo")).toBe(2);
  });

  it("returns zero for empty input", () => {
    expect(countParagraphs("   ")).toBe(0);
  });
});

describe("bandKeyFor", () => {
  it.each([
    [0, "human"],
    [34, "human"],
    [35, "uncertain"],
    [64, "uncertain"],
    [65, "ai"],
    [100, "ai"],
  ])("maps score %i to the %s band", (score, expected) => {
    expect(bandKeyFor(score, BANDS)).toBe(expected);
  });

  it("returns 'none' for a missing score rather than defaulting to a band", () => {
    expect(bandKeyFor(null, BANDS)).toBe("none");
  });

  it("uses the supplied bands rather than hard-coded thresholds", () => {
    const custom = [
      { lower: 0, upper: 49, label: "Likely human-patterned" },
      { lower: 50, upper: 100, label: "Likely AI-patterned" },
    ];
    expect(bandKeyFor(40, custom)).toBe("human");
    expect(bandKeyFor(60, custom)).toBe("ai");
  });

  it("has a style entry for every band key", () => {
    for (const key of ["human", "uncertain", "ai", "none"] as const) {
      expect(BAND_STYLES[key]).toBeDefined();
    }
  });
});

describe("formatBytes", () => {
  it.each([
    [512, "512 B"],
    [2048, "2 KB"],
    [5 * 1024 * 1024, "5 MB"],
  ])("formats %i as %s", (input, expected) => {
    expect(formatBytes(input)).toBe(expected);
  });
});

describe("formatDate", () => {
  it("renders a valid ISO date", () => {
    expect(formatDate("2026-03-01T10:00:00Z")).not.toBe("—");
  });

  it("returns a dash for an unparseable value", () => {
    expect(formatDate("not-a-date")).toBe("—");
  });
});

describe("messageForError", () => {
  it("maps known codes to guidance", () => {
    expect(messageForError("rate_limited", "fallback")).toContain("too many requests");
  });

  it("falls back to the server message for unknown codes", () => {
    expect(messageForError("something_new", "server said this")).toBe("server said this");
  });
});

function makeAnalysis(overrides: Partial<Analysis> = {}): Analysis {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    status: "completed",
    source: "text",
    source_filename: null,
    created_at: "2026-03-01T10:00:00Z",
    completed_at: "2026-03-01T10:00:02Z",
    label: "Uncertain or mixed signals",
    public_score: 50,
    raw_model_score: 0.5,
    reliability: "normal",
    reliability_reasons: [],
    counts: { words: 200, characters: 1200, paragraphs: 3 },
    detected_language: "en",
    language_confidence: 0.99,
    window_stability: 0.02,
    segments: [],
    integrity_warnings: [],
    diagnostics: { moving_average_ttr: 0.8 },
    model_metadata: { backend: "fake", is_real_model: false },
    calibration_version: "identity-1.0.0",
    detector_version: "1.0.0",
    failure_code: null,
    guest_token: null,
    stored_original_text: false,
    disclaimers: ["This score is an estimate, not proof of authorship."],
    ...overrides,
  };
}

describe("buildExport", () => {
  it("produces valid JSON", () => {
    expect(() => JSON.parse(buildExport(makeAnalysis()))).not.toThrow();
  });

  it("includes the score, provenance, and disclaimers", () => {
    const parsed = JSON.parse(buildExport(makeAnalysis()));
    expect(parsed.analysis.ai_signal_score).toBe(50);
    expect(parsed.provenance.calibration_version).toBe("identity-1.0.0");
    expect(parsed.disclaimers).toHaveLength(1);
  });

  it("always carries disclaimers so an exported file is never a bare number", () => {
    const parsed = JSON.parse(buildExport(makeAnalysis()));
    expect(parsed.disclaimers.length).toBeGreaterThan(0);
  });

  it("preserves a null score rather than coercing it to zero", () => {
    const parsed = JSON.parse(
      buildExport(makeAnalysis({ public_score: null, raw_model_score: null })),
    );
    expect(parsed.analysis.ai_signal_score).toBeNull();
  });
});

describe("bandKeyForLabel", () => {
  it.each([
    ["Likely human-patterned", "human"],
    ["Likely AI-patterned", "ai"],
    ["Uncertain or mixed signals", "uncertain"],
  ])("classifies %j as %s", (label, expected) => {
    expect(bandKeyForLabel(label)).toBe(expected);
  });

  it("does not classify 'Uncertain' as AI on the substring 'ai'", () => {
    // Regression: "uncert-ai-n" contains "ai", which a naive includes() check
    // matched, painting the whole middle band with the AI colour.
    expect(bandKeyForLabel("Uncertain or mixed signals")).not.toBe("ai");
  });

  it("returns 'none' for an unrecognised label rather than guessing", () => {
    expect(bandKeyForLabel("Something else entirely")).toBe("none");
  });
});
