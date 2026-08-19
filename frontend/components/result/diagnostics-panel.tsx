"use client";

import { useState } from "react";
import type { Analysis } from "@/lib/types";

interface Row {
  label: string;
  value: string;
  help: string;
}

function num(value: unknown, digits = 2): string {
  return typeof value === "number" ? value.toFixed(digits) : "—";
}

function nested(source: Record<string, unknown> | null, key: string): Record<string, unknown> {
  const value = source?.[key];
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

/**
 * Neutral statistics shown as context.
 *
 * These are explicitly *not* inputs to the score. The panel says so, because a
 * reader who sees numbers next to a verdict will otherwise assume they produced
 * it.
 */
export function DiagnosticsPanel({ analysis }: { analysis: Analysis }) {
  const [open, setOpen] = useState(false);
  const diagnostics = analysis.diagnostics;
  if (!diagnostics) return null;

  const sentences = nested(diagnostics, "sentence_lengths");
  const paragraphs = nested(diagnostics, "paragraph_lengths");

  const rows: Row[] = [
    {
      label: "Mean sentence length",
      value: `${num(sentences["mean"], 1)} words`,
      help: "Average number of words per sentence.",
    },
    {
      label: "Sentence length variation",
      value: num(sentences["coefficient_of_variation"]),
      help:
        "Spread of sentence lengths relative to their average. Lower means more uniform " +
        "sentences; uniformity is common in edited and in generated prose alike.",
    },
    {
      label: "Paragraph length variation",
      value: num(paragraphs["coefficient_of_variation"]),
      help: "Spread of paragraph lengths relative to their average.",
    },
    {
      label: "Lexical variety (MATTR)",
      value: num(diagnostics["moving_average_ttr"]),
      help:
        "Moving-average type-token ratio: distinct words per fixed window. Unlike a raw " +
        "ratio, it does not simply fall as the text gets longer.",
    },
    {
      label: "Repeated 3-grams",
      value: num(diagnostics["repeated_trigram_rate"], 3),
      help: "Share of three-word sequences that repeat elsewhere in the text.",
    },
    {
      label: "Repeated sentence openings",
      value: num(diagnostics["repeated_sentence_openings"], 3),
      help: "Share of sentences beginning with the same two words as an earlier sentence.",
    },
    {
      label: "Transition phrase density",
      value: `${num(diagnostics["transition_phrase_density"], 2)} per 100 words`,
      help:
        "Frequency of discourse markers such as 'however' or 'furthermore', counted from a " +
        "versioned list.",
    },
    {
      label: "Adjacent sentence similarity",
      value: num(diagnostics["consecutive_structural_similarity"]),
      help:
        "How alike neighbouring sentences are in length, clause count, and function-word " +
        "density. Higher means a more regular rhythm.",
    },
    {
      label: "Window agreement",
      value: num(diagnostics["window_consistency"]),
      help:
        "How closely the separately-scored sections of the text agreed. Low agreement " +
        "reduces reliability and can indicate mixed or edited writing.",
    },
  ];

  return (
    <section aria-labelledby="diagnostics-heading" className="card p-5 sm:p-7">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="diagnostics-heading" className="text-lg font-bold text-ink">
            Text statistics
          </h2>
          <p className="mt-1 max-w-prose text-sm text-ink-muted">
            Neutral measurements that describe the writing. They provide context and affect
            reliability, but they are <strong>not</strong> inputs to the score above.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls="diagnostics-table"
          className="no-print min-h-9 shrink-0 rounded-lg border border-line-strong px-3 text-sm font-semibold text-ink hover:bg-surface-sunken"
        >
          {open ? "Hide explanations" : "Explain these"}
        </button>
      </div>

      <div className="mt-5 overflow-x-auto">
        <table id="diagnostics-table" className="w-full min-w-[22rem] text-left text-sm">
          <caption className="sr-only">
            Deterministic text statistics for this submission
          </caption>
          <thead>
            <tr className="border-b border-line text-xs uppercase tracking-wide text-ink-muted">
              <th scope="col" className="py-2 pr-4 font-semibold">
                Measure
              </th>
              <th scope="col" className="py-2 font-semibold">
                Value
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="border-b border-line/60 align-top last:border-0">
                <th scope="row" className="py-3 pr-4 font-medium text-ink">
                  {row.label}
                  {open && (
                    <span className="mt-1 block max-w-prose text-xs font-normal text-ink-muted">
                      {row.help}
                    </span>
                  )}
                </th>
                <td className="py-3 tabular-nums text-ink-soft">{row.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
