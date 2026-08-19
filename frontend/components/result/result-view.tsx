"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Analysis } from "@/lib/types";
import { recallGuestToken } from "@/components/analyzer";
import { useConfig } from "@/components/config-provider";
import { Callout, Skeleton, Spinner } from "@/components/ui/feedback";
import { DiagnosticsPanel } from "./diagnostics-panel";
import { ResultDisclaimer } from "./disclaimer";
import { FeedbackForm } from "./feedback-form";
import { ParagraphMap } from "./paragraph-map";
import { ResultActions } from "./result-actions";
import { ScorePanel } from "./score-panel";

const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 120_000;

type LoadState = "loading" | "polling" | "ready" | "error" | "notfound";

/**
 * Fetches a result and, if the job is still running, polls until it settles.
 *
 * The interval is cleared on unmount and when the job reaches a terminal state,
 * and an AbortController cancels any request in flight, so navigating away
 * cannot leave a timer or a fetch running.
 */
export function ResultView({ analysisId }: { analysisId: string }) {
  const config = useConfig();
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [state, setState] = useState<LoadState>("loading");
  const [error, setError] = useState<string | null>(null);
  const guestToken = useRef<string | null>(null);
  const startedAt = useRef<number | null>(null);
  // Read during render would be impure; the value is mirrored into state when
  // the effect resolves it, so the render path stays deterministic.
  const [tokenForFeedback, setTokenForFeedback] = useState<string | null>(null);

  const load = useCallback(
    async (signal: AbortSignal): Promise<Analysis | null> => {
      const token = guestToken.current;
      return api.get<Analysis>(
        `/api/v1/analyses/${analysisId}`,
        token ? { token } : undefined,
        signal,
      );
    },
    [analysisId],
  );

  useEffect(() => {
    guestToken.current = recallGuestToken(analysisId);
    setTokenForFeedback(guestToken.current);
    startedAt.current = Date.now();
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    async function tick() {
      try {
        const result = await load(controller.signal);
        if (cancelled || !result) return;

        setAnalysis(result);

        if (result.status === "queued" || result.status === "running") {
          if (Date.now() - (startedAt.current ?? Date.now()) > POLL_TIMEOUT_MS) {
            setState("error");
            setError("This analysis is taking longer than expected. Try reloading shortly.");
            return;
          }
          setState("polling");
          timer = setTimeout(tick, POLL_INTERVAL_MS);
          return;
        }
        setState("ready");
      } catch (caught) {
        if (cancelled) return;
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        if (caught instanceof ApiError && caught.status === 404) {
          setState("notfound");
          return;
        }
        setState("error");
        setError(
          caught instanceof ApiError ? caught.message : "This result could not be loaded.",
        );
      }
    }

    void tick();

    return () => {
      cancelled = true;
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [analysisId, load]);

  if (state === "loading") {
    return (
      <div className="container-page max-w-4xl py-10">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-6 h-44 w-full" />
        <Skeleton className="mt-4 h-64 w-full" />
        <p className="sr-only">Loading result…</p>
      </div>
    );
  }

  if (state === "notfound") {
    return (
      <div className="container-page max-w-2xl py-16">
        <h1 className="text-2xl font-bold text-ink">This result is not available</h1>
        <p className="mt-3 text-ink-soft">
          It may have expired, or the link may be missing its access token. Guest results are
          removed after {config.guest_retention_hours} hours and can only be opened from the
          browser session that created them.
        </p>
        <Link
          href="/analyze"
          className="mt-6 inline-flex min-h-11 items-center rounded-lg bg-brand px-5 text-sm font-semibold text-white hover:bg-brand-hover"
        >
          Analyze something new
        </Link>
      </div>
    );
  }

  if (state === "error" || !analysis) {
    return (
      <div className="container-page max-w-2xl py-16">
        <Callout tone="error" title="Could not load this result">
          {error ?? "An unexpected error occurred."}
        </Callout>
        <Link href="/analyze" className="mt-6 inline-block font-semibold text-brand underline">
          Back to the analyzer
        </Link>
      </div>
    );
  }

  if (analysis.status === "failed") {
    return (
      <div className="container-page max-w-2xl py-16">
        <Callout tone="error" title="This analysis did not complete">
          <p>
            No result was produced. Nothing was scored, so there is nothing to interpret.
          </p>
          {analysis.failure_code && (
            <p className="mt-2 font-mono text-xs">Reason code: {analysis.failure_code}</p>
          )}
        </Callout>
        <Link href="/analyze" className="mt-6 inline-block font-semibold text-brand underline">
          Try again
        </Link>
      </div>
    );
  }

  return (
    <div className="container-page max-w-4xl py-8 sm:py-12">
      <div className="no-print flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-ink">Analysis result</h1>
          <p className="mt-1 text-sm text-ink-muted">
            {formatDate(analysis.created_at)} · {analysis.counts.words.toLocaleString()} words
            {analysis.source_filename && ` · ${analysis.source_filename}`}
          </p>
        </div>
        <ResultActions analysis={analysis} />
      </div>

      {state === "polling" && (
        <div className="mt-6">
          <Spinner label="Analysis in progress — this page will update automatically." />
        </div>
      )}

      <div className="mt-6 flex flex-col gap-6">
        <ScorePanel analysis={analysis} bands={config.bands} />

        <ResultDisclaimer
          disclaimers={
            analysis.disclaimers.length > 0 ? analysis.disclaimers : config.disclaimers
          }
        />

        {analysis.integrity_warnings.length > 0 && (
          <Callout tone="warning" title="Content integrity notes">
            <ul className="list-disc space-y-1 pl-5">
              {analysis.integrity_warnings.map((warning) => (
                <li key={warning.code}>{warning.message}</li>
              ))}
            </ul>
          </Callout>
        )}

        <ParagraphMap segments={analysis.segments} bands={config.bands} />
        <DiagnosticsPanel analysis={analysis} />

        <section aria-labelledby="provenance-heading" className="card p-5 sm:p-7">
          <h2 id="provenance-heading" className="text-lg font-bold text-ink">
            How this result was produced
          </h2>
          <dl className="mt-4 grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="font-medium text-ink-muted">Detector version</dt>
              <dd className="text-ink">{analysis.detector_version ?? "—"}</dd>
            </div>
            <div>
              <dt className="font-medium text-ink-muted">Calibration</dt>
              <dd className="text-ink">{analysis.calibration_version ?? "—"}</dd>
            </div>
            <div>
              <dt className="font-medium text-ink-muted">Detected language</dt>
              <dd className="text-ink">{analysis.detected_language ?? "—"}</dd>
            </div>
            <div>
              <dt className="font-medium text-ink-muted">Section agreement</dt>
              <dd className="text-ink">
                {analysis.window_stability === null
                  ? "—"
                  : analysis.window_stability.toFixed(3)}
              </dd>
            </div>
          </dl>
          {analysis.model_metadata?.["is_real_model"] === false && (
            <Callout tone="warning" className="mt-4">
              This result came from the deterministic test detector, not a trained model. It
              is meaningless as a classification.
            </Callout>
          )}
        </section>

        <FeedbackForm analysisId={analysis.id} guestToken={tokenForFeedback} />
      </div>
    </div>
  );
}
