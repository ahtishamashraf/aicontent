"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { BAND_STYLES, RELIABILITY_LABELS, bandKeyFor, formatDate } from "@/lib/format";
import type { AnalysisSummary, Paged } from "@/lib/types";
import { useConfig } from "@/components/config-provider";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Callout, EmptyState, Skeleton } from "@/components/ui/feedback";

const PAGE_SIZE = 10;

type StatusFilter = "" | "completed" | "failed" | "queued" | "running";
type SourceFilter = "" | "text" | "document";

export function HistoryTable() {
  const config = useConfig();
  const [data, setData] = useState<Paged<AnalysisSummary> | null>(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<StatusFilter>("");
  const [source, setSource] = useState<SourceFilter>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await api.get<Paged<AnalysisSummary>>("/api/v1/analyses", {
          page,
          page_size: PAGE_SIZE,
          status: status || undefined,
          source: source || undefined,
        }),
      );
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load your history.");
    } finally {
      setLoading(false);
    }
  }, [page, status, source]);

  useEffect(() => {
    // Yield before the first setState so it is not synchronous with the effect.
    let cancelled = false;
    void (async () => {
      await Promise.resolve();
      if (!cancelled) await load();
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  async function remove(id: string) {
    setBusy(true);
    try {
      await api.delete(`/api/v1/analyses/${id}`);
      setPendingDelete(null);
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Deletion failed.");
    } finally {
      setBusy(false);
    }
  }

  async function removeAll() {
    setBusy(true);
    try {
      await api.delete("/api/v1/analyses");
      setConfirmDeleteAll(false);
      setPage(1);
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Deletion failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label htmlFor="filter-status" className="text-sm font-semibold text-ink">
            Status
          </label>
          <select
            id="filter-status"
            value={status}
            onChange={(event) => {
              setStatus(event.target.value as StatusFilter);
              setPage(1);
            }}
            className="min-h-10 rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink"
          >
            <option value="">All</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="queued">Queued</option>
            <option value="running">Running</option>
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="filter-source" className="text-sm font-semibold text-ink">
            Source
          </label>
          <select
            id="filter-source"
            value={source}
            onChange={(event) => {
              setSource(event.target.value as SourceFilter);
              setPage(1);
            }}
            className="min-h-10 rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink"
          >
            <option value="">All</option>
            <option value="text">Pasted text</option>
            <option value="document">Document</option>
          </select>
        </div>

        {data && data.total > 0 && (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setConfirmDeleteAll(true)}
            className="ml-auto"
          >
            Delete all
          </Button>
        )}
      </div>

      {error && (
        <Callout tone="error" className="mt-5">
          {error}
        </Callout>
      )}

      {loading && !data ? (
        <div className="mt-6 flex flex-col gap-3">
          {[0, 1, 2].map((row) => (
            <Skeleton key={row} className="h-20 w-full" />
          ))}
          <p className="sr-only">Loading your analyses…</p>
        </div>
      ) : data && data.items.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title={status || source ? "Nothing matches those filters" : "No analyses yet"}
            description={
              status || source
                ? "Try clearing the filters to see everything."
                : "Analyses you run while signed in will appear here."
            }
            action={
              <Link
                href="/analyze"
                className="inline-flex min-h-11 items-center rounded-lg bg-brand px-5 text-sm font-semibold text-white hover:bg-brand-hover"
              >
                Analyze something
              </Link>
            }
          />
        </div>
      ) : (
        data && (
          <>
            <ul className="mt-6 flex flex-col gap-3 sm:hidden">
              {data.items.map((item) => {
                const styles = BAND_STYLES[bandKeyFor(item.public_score, config.bands)];
                return (
                  <li key={item.id} className="card p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="font-semibold text-ink">{item.label ?? "No result"}</p>
                        <p className="mt-1 text-xs text-ink-muted">
                          {formatDate(item.created_at)}
                        </p>
                      </div>
                      <span className={`shrink-0 text-2xl font-bold tabular-nums ${styles.text}`}>
                        {item.public_score ?? "—"}
                      </span>
                    </div>
                    <div className="mt-3 flex items-center gap-4">
                      <Link
                        href={`/result/${item.id}`}
                        className="text-sm font-semibold text-brand hover:underline"
                      >
                        View
                      </Link>
                      <button
                        type="button"
                        onClick={() => setPendingDelete(item.id)}
                        className="text-sm font-semibold text-danger hover:underline"
                      >
                        Delete
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>

            <div className="mt-6 hidden overflow-x-auto sm:block">
              <table className="w-full min-w-[40rem] text-left text-sm">
                <caption className="sr-only">Your previous analyses</caption>
                <thead>
                  <tr className="border-b border-line text-xs uppercase tracking-wide text-ink-muted">
                    <th scope="col" className="py-2 pr-4 font-semibold">Date</th>
                    <th scope="col" className="py-2 pr-4 font-semibold">Result</th>
                    <th scope="col" className="py-2 pr-4 font-semibold">Score</th>
                    <th scope="col" className="py-2 pr-4 font-semibold">Reliability</th>
                    <th scope="col" className="py-2 pr-4 font-semibold">Words</th>
                    <th scope="col" className="py-2 font-semibold">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => {
                    const styles = BAND_STYLES[bandKeyFor(item.public_score, config.bands)];
                    return (
                      <tr key={item.id} className="border-b border-line/60 last:border-0">
                        <td className="py-3 pr-4 text-ink-soft">{formatDate(item.created_at)}</td>
                        <td className="py-3 pr-4 font-medium text-ink">
                          {item.label ?? "No result"}
                        </td>
                        <td className={`py-3 pr-4 font-bold tabular-nums ${styles.text}`}>
                          {item.public_score ?? "—"}
                        </td>
                        <td className="py-3 pr-4 text-ink-soft">
                          {item.reliability ? RELIABILITY_LABELS[item.reliability] : "—"}
                        </td>
                        <td className="py-3 pr-4 tabular-nums text-ink-soft">
                          {item.word_count.toLocaleString()}
                        </td>
                        <td className="py-3">
                          <div className="flex justify-end gap-4">
                            <Link
                              href={`/result/${item.id}`}
                              className="font-semibold text-brand hover:underline"
                            >
                              View
                            </Link>
                            <button
                              type="button"
                              onClick={() => setPendingDelete(item.id)}
                              className="font-semibold text-danger hover:underline"
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {data.total_pages > 1 && (
              <nav
                aria-label="Pagination"
                className="mt-6 flex items-center justify-between gap-3"
              >
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((value) => Math.max(1, value - 1))}
                >
                  Previous
                </Button>
                <p aria-live="polite" className="text-sm text-ink-muted">
                  Page {data.page} of {data.total_pages}
                </p>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page >= data.total_pages}
                  onClick={() => setPage((value) => value + 1)}
                >
                  Next
                </Button>
              </nav>
            )}
          </>
        )
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete this analysis?"
        description="The result and any text you chose to keep are removed permanently. This cannot be undone."
        confirmLabel="Delete"
        destructive
        busy={busy}
        onConfirm={() => pendingDelete && remove(pendingDelete)}
        onCancel={() => setPendingDelete(null)}
      />

      <ConfirmDialog
        open={confirmDeleteAll}
        title="Delete every analysis?"
        description="Your entire history and any retained text are removed permanently. This cannot be undone."
        confirmLabel="Delete everything"
        destructive
        busy={busy}
        onConfirm={removeAll}
        onCancel={() => setConfirmDeleteAll(false)}
      />
    </div>
  );
}
