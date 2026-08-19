/** Presentation helpers shared by the analyzer, result, and dashboard views. */

import type { Analysis, Band, Reliability } from "./types";

/** Word count using the same whitespace rule as the backend. */
export function countWords(text: string): number {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

export function countParagraphs(text: string): number {
  const trimmed = text.trim();
  return trimmed ? trimmed.split(/\n\s*\n/).filter((p) => p.trim()).length : 0;
}

export type BandKey = "human" | "uncertain" | "ai" | "none";

/**
 * Classify a band label into a style key.
 *
 * Matching is on whole words. A plain substring test is a trap here: "ai" is
 * inside "uncertain", so `label.includes("ai")` classifies the entire middle
 * band as AI-patterned and paints it with the wrong colour.
 */
export function bandKeyForLabel(label: string): BandKey {
  const words = label.toLowerCase().split(/[^a-z]+/).filter(Boolean);
  if (words.includes("uncertain") || words.includes("mixed")) return "uncertain";
  if (words.includes("human")) return "human";
  if (words.includes("ai")) return "ai";
  return "none";
}

/**
 * Map a score to a band key using the *server's* band table, so the frontend
 * never hard-codes a threshold.
 */
export function bandKeyFor(score: number | null, bands: Band[]): BandKey {
  if (score === null) return "none";
  const band = bands.find((b) => score >= b.lower && score <= b.upper);
  return band ? bandKeyForLabel(band.label) : "none";
}

/** Tailwind classes per band. Colour is never the only signal — text accompanies it. */
export const BAND_STYLES: Record<BandKey, { text: string; bg: string; border: string }> = {
  human: { text: "text-band-human", bg: "bg-band-humanSoft", border: "border-band-human/30" },
  uncertain: {
    text: "text-band-uncertain",
    bg: "bg-band-uncertainSoft",
    border: "border-band-uncertain/30",
  },
  ai: { text: "text-band-ai", bg: "bg-band-aiSoft", border: "border-band-ai/30" },
  none: { text: "text-ink-muted", bg: "bg-surface-sunken", border: "border-line" },
};

export const RELIABILITY_LABELS: Record<Reliability, string> = {
  insufficient: "Not enough text",
  low: "Low reliability",
  moderate: "Moderate reliability",
  normal: "Normal reliability",
};

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(bytes % (1024 * 1024) === 0 ? 0 : 1)} MB`;
}

/**
 * Build the JSON export payload.
 *
 * The export mirrors what the user can already see, and always carries the
 * disclaimers and provenance so a file passed to someone else does not arrive
 * as a bare number.
 */
export function buildExport(analysis: Analysis): string {
  return JSON.stringify(
    {
      exported_at: new Date().toISOString(),
      analysis: {
        id: analysis.id,
        created_at: analysis.created_at,
        source: analysis.source,
        source_filename: analysis.source_filename,
        label: analysis.label,
        ai_signal_score: analysis.public_score,
        raw_model_score: analysis.raw_model_score,
        reliability: analysis.reliability,
        reliability_reasons: analysis.reliability_reasons,
        counts: analysis.counts,
        detected_language: analysis.detected_language,
        window_stability: analysis.window_stability,
        integrity_warnings: analysis.integrity_warnings,
        segments: analysis.segments.map((segment) => ({
          id: segment.id,
          index: segment.index,
          word_count: segment.word_count,
          ai_signal_score: segment.public_score,
          label: segment.label,
          too_short: segment.too_short,
          grouped_with_context: segment.grouped_with_context,
        })),
        diagnostics: analysis.diagnostics,
      },
      provenance: {
        model: analysis.model_metadata,
        calibration_version: analysis.calibration_version,
        detector_version: analysis.detector_version,
      },
      disclaimers: analysis.disclaimers,
    },
    null,
    2,
  );
}

/** Human-readable messages for API failure codes surfaced in the analyzer. */
export const FAILURE_MESSAGES: Record<string, string> = {
  rate_limited: "You have made too many requests. Please wait a little and try again.",
  payload_too_large: "That submission is larger than the current limit.",
  document_rejected: "That file could not be processed safely.",
  unsupported_media_type: "Only .txt, .pdf, and .docx files are accepted.",
  analysis_unavailable:
    "Analysis is temporarily unavailable. No result was produced — please try again shortly.",
  validation_failed: "Please check the submitted values and try again.",
};

export function messageForError(code: string, fallback: string): string {
  return FAILURE_MESSAGES[code] ?? fallback;
}
