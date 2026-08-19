"use client";

import { BAND_STYLES, RELIABILITY_LABELS, bandKeyFor, bandKeyForLabel } from "@/lib/format";
import type { Analysis, Band } from "@/lib/types";

const BAND_FILL: Record<string, string> = {
  human: "#2f6b4f",
  ai: "#8c4a2f",
  uncertain: "#8a6412",
  none: "#c3cad3",
};

/**
 * The headline result.
 *
 * Colour never carries meaning alone: the band label is always written out, and
 * the reliability and its reasons sit beside the number rather than behind a
 * tooltip. A missing score renders as an explanation, never as "0".
 */
export function ScorePanel({ analysis, bands }: { analysis: Analysis; bands: Band[] }) {
  const key = bandKeyFor(analysis.public_score, bands);
  const styles = BAND_STYLES[key];
  const hasScore = analysis.public_score !== null;

  return (
    <section
      aria-labelledby="score-heading"
      className={`card border ${styles.border} ${styles.bg} p-5 sm:p-7`}
    >
      {/* Distinct from the page's "Analysis result" h1: two headings sharing a
          name makes heading-by-heading navigation ambiguous. */}
      <h2 id="score-heading" className="sr-only">
        Overall AI signal score
      </h2>

      <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-muted">
            AI signal score
          </p>
          <p className={`mt-2 text-2xl font-bold sm:text-3xl ${styles.text}`}>
            {analysis.label ?? "No result"}
          </p>

          {analysis.reliability && (
            <p className="mt-3 inline-flex items-center gap-2 rounded-pill bg-surface/70 px-3 py-1 text-sm font-medium text-ink-soft">
              {RELIABILITY_LABELS[analysis.reliability]}
            </p>
          )}
        </div>

        {hasScore ? (
          <p className="shrink-0 sm:text-right">
            <span className={`text-5xl font-black tabular-nums sm:text-6xl ${styles.text}`}>
              {analysis.public_score}
            </span>
            <span className="text-xl font-semibold text-ink-muted">/100</span>
          </p>
        ) : (
          <p className="shrink-0 text-sm text-ink-muted sm:max-w-[16rem] sm:text-right">
            <span className="font-semibold">No score</span>
            <span className="mt-1 block text-xs">
              A number here would imply a confidence the analyser does not have.
            </span>
          </p>
        )}
      </div>

      {hasScore && (
        <div className="mt-6">
          <div
            role="img"
            aria-label={`Score ${analysis.public_score} out of 100, in the band "${analysis.label}"`}
            className="relative h-3 w-full overflow-hidden rounded-pill bg-surface"
          >
            {bands.map((band) => (
              <span
                key={band.label}
                className="absolute inset-y-0 opacity-30"
                style={{
                  left: `${band.lower}%`,
                  width: `${band.upper - band.lower + 1}%`,
                  backgroundColor: BAND_FILL[bandKeyForLabel(band.label)],
                }}
              />
            ))}
            <span
              className="absolute top-1/2 h-5 w-1 -translate-y-1/2 rounded-full bg-ink ring-2 ring-surface"
              style={{ left: `calc(${analysis.public_score}% - 2px)` }}
            />
          </div>
          <ul className="mt-2 flex justify-between gap-2 text-xs text-ink-muted">
            {bands.map((band) => (
              <li key={band.label} className="min-w-0 flex-1 text-center">
                <span className="tabular-nums">
                  {band.lower}–{band.upper}
                </span>
                <span className="mt-0.5 block leading-tight">{band.label}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {analysis.reliability_reasons.length > 0 && (
        <div className="mt-6 rounded-lg bg-surface/70 p-4">
          <h3 className="text-sm font-semibold text-ink">Why this reliability</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-soft">
            {analysis.reliability_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
