/**
 * Public configuration, fetched once from the API.
 *
 * Limits, band thresholds, disclaimers, and product identity all live on the
 * server. Duplicating them here would guarantee they drift.
 */

import type { PublicConfig } from "./types";

/**
 * Used before the API responds and if it is unreachable, so the UI can render
 * something coherent rather than blank. Values are conservative and are
 * replaced by the server's as soon as they arrive.
 */
export const FALLBACK_CONFIG: PublicConfig = {
  product_name: "OriginLens",
  tagline:
    "Evidence-based signals about how writing was produced — never a verdict on who wrote it.",
  support_email: "support@originlens.local",
  min_words: 80,
  low_reliability_words: 150,
  max_words: 10000,
  max_characters: 50000,
  max_upload_bytes: 5242880,
  allowed_extensions: [".docx", ".pdf", ".txt"],
  bands: [
    { lower: 0, upper: 34, label: "Likely human-patterned" },
    { lower: 35, upper: 64, label: "Uncertain or mixed signals" },
    { lower: 65, upper: 100, label: "Likely AI-patterned" },
  ],
  disclaimers: [
    "This score is an estimate of stylistic patterns, not proof of authorship.",
    "Edited, paraphrased, translated, formulaic, or highly technical writing can be misclassified in either direction.",
    "The analyser is validated for English only.",
    "Do not make a consequential decision about a person from this result alone. Use human judgement and additional evidence.",
  ],
  guest_retention_hours: 24,
};
