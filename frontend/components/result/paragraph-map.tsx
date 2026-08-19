"use client";

import { useState } from "react";
import { BAND_STYLES, bandKeyFor } from "@/lib/format";
import type { Band, Segment } from "@/lib/types";

/**
 * Per-paragraph scores.
 *
 * Every colour here comes from that paragraph's own score. Paragraphs without
 * enough evidence are shown as "not scored" rather than being tinted toward a
 * band they were never measured against.
 */
export function ParagraphMap({ segments, bands }: { segments: Segment[]; bands: Band[] }) {
  const [selected, setSelected] = useState<string | null>(null);
  const scored = segments.filter((segment) => segment.public_score !== null);

  if (segments.length === 0) return null;

  return (
    <section aria-labelledby="paragraphs-heading" className="card p-5 sm:p-7">
      <h2 id="paragraphs-heading" className="text-lg font-bold text-ink">
        Paragraph breakdown
      </h2>
      <p className="mt-1 text-sm text-ink-muted">
        {scored.length} of {segments.length} paragraphs had enough text to score individually.
      </p>

      <ol className="mt-5 flex flex-col gap-2">
        {segments.map((segment) => {
          const key = bandKeyFor(segment.public_score, bands);
          const styles = BAND_STYLES[key];
          const isActive = segment.id === selected;
          return (
            <li key={segment.id}>
              <button
                type="button"
                onClick={() => setSelected(isActive ? null : segment.id)}
                aria-expanded={isActive}
                aria-controls={`segment-detail-${segment.id}`}
                className={[
                  "flex w-full items-center gap-3 rounded-lg border px-3 py-3 text-left transition-colors",
                  isActive ? "border-brand bg-brand-soft" : "border-line hover:bg-surface-sunken",
                ].join(" ")}
              >
                <span
                  aria-hidden="true"
                  className={`h-8 w-1.5 shrink-0 rounded-full ${styles.bg} ring-1 ring-inset ${styles.border}`}
                />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold text-ink">
                    Paragraph {segment.index + 1}
                  </span>
                  <span className="block text-xs text-ink-muted">
                    {segment.word_count} words
                    {segment.grouped_with_context && " · scored with surrounding context"}
                  </span>
                </span>
                <span className="shrink-0 text-right">
                  {segment.public_score === null ? (
                    <span className="text-xs font-medium text-ink-muted">Not scored</span>
                  ) : (
                    <span className={`text-lg font-bold tabular-nums ${styles.text}`}>
                      {segment.public_score}
                    </span>
                  )}
                </span>
              </button>

              {isActive && (
                <div
                  id={`segment-detail-${segment.id}`}
                  className="mt-1 rounded-lg border border-line bg-surface-sunken p-4 text-sm"
                >
                  {segment.too_short ? (
                    <p className="text-ink-soft">
                      This paragraph is too short to score on its own. Showing a number for it
                      would suggest a precision the analyser cannot support.
                    </p>
                  ) : (
                    <p className="text-ink-soft">
                      Band: <strong className="text-ink">{segment.label}</strong>
                      {segment.grouped_with_context &&
                        " — scored together with neighbouring paragraphs because it is short on its own."}
                    </p>
                  )}
                  {segment.text && (
                    <blockquote className="mt-3 border-l-2 border-line-strong pl-3 italic text-ink-soft">
                      {segment.text}
                    </blockquote>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
