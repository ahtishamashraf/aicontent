import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { vi } from "vitest";
import { FALLBACK_CONFIG } from "@/lib/config";
import type { Analysis, Segment } from "@/lib/types";

// Router spies live in tests/setup.ts, where vi.mock applies to every file.
export { routerPush, routerReplace } from "./setup";

export function renderWithProviders(ui: ReactElement, options?: RenderOptions) {
  return render(ui, options);
}

export const BANDS = FALLBACK_CONFIG.bands;

export function makeSegment(overrides: Partial<Segment> = {}): Segment {
  return {
    id: "p-000",
    index: 0,
    text: null,
    word_count: 120,
    character_count: 700,
    public_score: 42,
    raw_model_score: 0.42,
    label: "Uncertain or mixed signals",
    too_short: false,
    grouped_with_context: false,
    ...overrides,
  };
}

export function makeAnalysis(overrides: Partial<Analysis> = {}): Analysis {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    status: "completed",
    source: "text",
    source_filename: null,
    created_at: "2026-03-01T10:00:00Z",
    completed_at: "2026-03-01T10:00:02Z",
    label: "Likely AI-patterned",
    public_score: 78,
    raw_model_score: 0.78,
    reliability: "normal",
    reliability_reasons: [],
    counts: { words: 320, characters: 1900, paragraphs: 2 },
    detected_language: "en",
    language_confidence: 0.99,
    window_stability: 0.02,
    segments: [makeSegment(), makeSegment({ id: "p-001", index: 1 })],
    integrity_warnings: [],
    diagnostics: {
      sentence_lengths: { mean: 18.4, coefficient_of_variation: 0.42 },
      paragraph_lengths: { coefficient_of_variation: 0.3 },
      moving_average_ttr: 0.81,
      repeated_trigram_rate: 0.004,
      repeated_sentence_openings: 0.0,
      transition_phrase_density: 1.2,
      consecutive_structural_similarity: 0.55,
      window_consistency: 0.96,
    },
    model_metadata: { backend: "fake", is_real_model: false },
    calibration_version: "identity-1.0.0",
    detector_version: "1.0.0",
    failure_code: null,
    guest_token: null,
    stored_original_text: false,
    disclaimers: [
      "This score is an estimate of stylistic patterns, not proof of authorship.",
      "The analyser is validated for English only.",
    ],
    ...overrides,
  };
}

/** Minimal fetch stub returning a JSON body with the given status. */
export function stubFetch(handler: (url: string, init?: RequestInit) => {
  status?: number;
  body?: unknown;
}) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const { status = 200, body = {} } = handler(url, init);
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  globalThis.fetch = spy as unknown as typeof fetch;
  return spy;
}

export function Wrapper({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
