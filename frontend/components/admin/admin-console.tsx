"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type {
  AdminStats,
  AdminUser,
  ModelHealth,
  Paged,
} from "@/lib/types";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { TextAreaField } from "@/components/ui/field";
import { Callout, EmptyState, Skeleton } from "@/components/ui/feedback";

interface AuditEntry {
  id: string;
  created_at: string;
  actor_user_id: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  context: Record<string, unknown> | null;
}

type Tab = "overview" | "users" | "health" | "audit";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "users", label: "Users" },
  { id: "health", label: "Service health" },
  { id: "audit", label: "Audit log" },
];

export function AdminConsole() {
  const [tab, setTab] = useState<Tab>("overview");

  return (
    <div>
      <div role="tablist" aria-label="Administration sections" className="flex flex-wrap gap-1 border-b border-line">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            role="tab"
            type="button"
            aria-selected={tab === entry.id}
            aria-controls={`admin-panel-${entry.id}`}
            id={`admin-tab-${entry.id}`}
            onClick={() => setTab(entry.id)}
            className={[
              "min-h-11 rounded-t-lg px-4 text-sm font-semibold transition-colors",
              tab === entry.id
                ? "border-b-2 border-brand text-brand"
                : "text-ink-muted hover:text-ink",
            ].join(" ")}
          >
            {entry.label}
          </button>
        ))}
      </div>

      <div
        id={`admin-panel-${tab}`}
        role="tabpanel"
        aria-labelledby={`admin-tab-${tab}`}
        className="pt-8"
      >
        {tab === "overview" && <StatsPanel />}
        {tab === "users" && <UsersPanel />}
        {tab === "health" && <HealthPanel />}
        {tab === "audit" && <AuditPanel />}
      </div>
    </div>
  );
}

function StatsPanel() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .get<AdminStats>("/api/v1/admin/stats", undefined, controller.signal)
      .then(setStats)
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        setError(caught instanceof ApiError ? caught.message : "Could not load statistics.");
      });
    return () => controller.abort();
  }, []);

  if (error) return <Callout tone="error">{error}</Callout>;
  if (!stats) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
    );
  }

  const cards = [
    { label: "Users", value: stats.users_total, note: `${stats.users_active} active` },
    { label: "Suspended", value: stats.users_suspended, note: "accounts" },
    {
      label: "Analyses",
      value: stats.analyses_total,
      note: `${stats.analyses_last_24h} in last 24h`,
    },
    { label: "Feedback", value: stats.feedback_total, note: "responses" },
  ];

  return (
    <>
      <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <div key={card.label} className="card p-5">
            <dt className="text-sm font-medium text-ink-muted">{card.label}</dt>
            <dd className="mt-1 text-3xl font-bold tabular-nums text-ink">
              {card.value.toLocaleString()}
            </dd>
            <p className="mt-1 text-xs text-ink-muted">{card.note}</p>
          </div>
        ))}
      </dl>
      <div className="mt-6 card p-5">
        <h3 className="font-semibold text-ink">Analysis outcomes</h3>
        <p className="mt-2 text-sm text-ink-soft">
          {stats.analyses_completed.toLocaleString()} completed ·{" "}
          {stats.analyses_failed.toLocaleString()} failed
        </p>
        <p className="mt-3 text-xs text-ink-muted">
          These are counts only. No submitted text is reachable from this console.
        </p>
      </div>
    </>
  );
}

function UsersPanel() {
  const [data, setData] = useState<Paged<AdminUser> | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [target, setTarget] = useState<AdminUser | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(
        await api.get<Paged<AdminUser>>("/api/v1/admin/users", {
          page,
          page_size: 25,
          search: search || undefined,
        }),
      );
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load users.");
    }
  }, [page, search]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      await Promise.resolve();
      if (!cancelled) await load();
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  async function suspend() {
    if (!target) return;
    setBusy(true);
    try {
      await api.post(`/api/v1/admin/users/${target.id}/suspend`, { reason });
      setNotice(`${target.email} was suspended.`);
      setTarget(null);
      setReason("");
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Suspension failed.");
    } finally {
      setBusy(false);
    }
  }

  async function reactivate(user: AdminUser) {
    try {
      await api.post(`/api/v1/admin/users/${user.id}/reactivate`);
      setNotice(`${user.email} was reactivated.`);
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Reactivation failed.");
    }
  }

  return (
    <div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setPage(1);
          void load();
        }}
        className="flex flex-wrap items-end gap-3"
      >
        <div className="flex min-w-0 flex-1 flex-col gap-1 sm:max-w-sm">
          <label htmlFor="admin-search" className="text-sm font-semibold text-ink">
            Search by email
          </label>
          <input
            id="admin-search"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="min-h-10 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink"
          />
        </div>
        <Button type="submit" size="sm" variant="secondary">
          Search
        </Button>
      </form>

      {notice && (
        <Callout tone="success" className="mt-5">
          {notice}
        </Callout>
      )}
      {error && (
        <Callout tone="error" className="mt-5">
          {error}
        </Callout>
      )}

      {!data ? (
        <Skeleton className="mt-6 h-48 w-full" />
      ) : data.items.length === 0 ? (
        <div className="mt-6">
          <EmptyState title="No accounts found" description="Try a different search term." />
        </div>
      ) : (
        <div className="mt-6 overflow-x-auto">
          <table className="w-full min-w-[42rem] text-left text-sm">
            <caption className="sr-only">Registered accounts</caption>
            <thead>
              <tr className="border-b border-line text-xs uppercase tracking-wide text-ink-muted">
                <th scope="col" className="py-2 pr-4 font-semibold">Email</th>
                <th scope="col" className="py-2 pr-4 font-semibold">Role</th>
                <th scope="col" className="py-2 pr-4 font-semibold">Status</th>
                <th scope="col" className="py-2 pr-4 font-semibold">Joined</th>
                <th scope="col" className="py-2 font-semibold">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((user) => (
                <tr key={user.id} className="border-b border-line/60 last:border-0">
                  <td className="py-3 pr-4 break-all text-ink">{user.email}</td>
                  <td className="py-3 pr-4 text-ink-soft">{user.role}</td>
                  <td className="py-3 pr-4">
                    <span
                      className={[
                        "rounded-pill px-2 py-0.5 text-xs font-semibold",
                        user.status === "active"
                          ? "bg-success-soft text-success"
                          : user.status === "suspended"
                            ? "bg-danger-soft text-danger"
                            : "bg-surface-sunken text-ink-muted",
                      ].join(" ")}
                    >
                      {user.status}
                    </span>
                  </td>
                  <td className="py-3 pr-4 text-ink-soft">{formatDate(user.created_at)}</td>
                  <td className="py-3 text-right">
                    {user.status === "suspended" ? (
                      <button
                        type="button"
                        onClick={() => reactivate(user)}
                        className="font-semibold text-brand hover:underline"
                      >
                        Reactivate
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setTarget(user)}
                        className="font-semibold text-danger hover:underline"
                      >
                        Suspend
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.total_pages > 1 && (
        <nav aria-label="Pagination" className="mt-6 flex items-center justify-between gap-3">
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

      <ConfirmDialog
        open={target !== null}
        title={`Suspend ${target?.email ?? ""}?`}
        description="The account is signed out immediately and cannot sign in until reactivated."
        confirmLabel="Suspend account"
        destructive
        busy={busy}
        onConfirm={suspend}
        onCancel={() => {
          setTarget(null);
          setReason("");
        }}
      >
        <div className="mt-4">
          <TextAreaField
            label="Reason"
            hint="Recorded in the audit log. Minimum 3 characters."
            required
            rows={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </div>
      </ConfirmDialog>
    </div>
  );
}

function HealthPanel() {
  const [health, setHealth] = useState<ModelHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .get<ModelHealth>("/api/v1/admin/health/model", undefined, controller.signal)
      .then(setHealth)
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        setError(caught instanceof ApiError ? caught.message : "Could not load model health.");
      });
    return () => controller.abort();
  }, []);

  if (error) return <Callout tone="error">{error}</Callout>;
  if (!health) return <Skeleton className="h-40 w-full" />;

  return (
    <div className="flex flex-col gap-5">
      {!health.is_real_model && (
        <Callout tone="warning" title="Test detector in use">
          This deployment is running the deterministic fake detector. Results are not
          classifications. Production configuration refuses this backend.
        </Callout>
      )}
      {health.load_error_code && (
        <Callout tone="error" title="Model failed to load">
          <p className="font-mono text-xs">{health.load_error_code}</p>
          {health.load_error_detail && <p className="mt-1">{health.load_error_detail}</p>}
        </Callout>
      )}

      <section className="card p-5">
        <h3 className="font-semibold text-ink">Detector</h3>
        <dl className="mt-4 grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="font-medium text-ink-muted">Backend</dt>
            <dd className="text-ink">{health.backend}</dd>
          </div>
          <div>
            <dt className="font-medium text-ink-muted">Real model</dt>
            <dd className="text-ink">{health.is_real_model ? "Yes" : "No"}</dd>
          </div>
          <div>
            <dt className="font-medium text-ink-muted">Loaded</dt>
            <dd className="text-ink">{health.loaded ? "Yes" : "Not yet"}</dd>
          </div>
        </dl>

        {health.model && (
          <div className="mt-5 overflow-x-auto">
            <h4 className="text-sm font-semibold text-ink">Model provenance</h4>
            <dl className="mt-2 grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
              {Object.entries(health.model).map(([key, value]) => (
                <div key={key}>
                  <dt className="font-medium text-ink-muted">{key.replace(/_/g, " ")}</dt>
                  <dd className="break-all text-ink">{String(value)}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </section>
    </div>
  );
}

function AuditPanel() {
  const [data, setData] = useState<Paged<AuditEntry> | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .get<Paged<AuditEntry>>("/api/v1/admin/audit-logs", { page, page_size: 50 }, controller.signal)
      .then(setData)
      .catch((caught: unknown) => {
        if (caught instanceof DOMException && caught.name === "AbortError") return;
        setError(caught instanceof ApiError ? caught.message : "Could not load the audit log.");
      });
    return () => controller.abort();
  }, [page]);

  if (error) return <Callout tone="error">{error}</Callout>;
  if (!data) return <Skeleton className="h-48 w-full" />;
  if (data.items.length === 0) {
    return <EmptyState title="No audit entries" description="Administrative actions appear here." />;
  }

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[38rem] text-left text-sm">
          <caption className="sr-only">Administrative and security events</caption>
          <thead>
            <tr className="border-b border-line text-xs uppercase tracking-wide text-ink-muted">
              <th scope="col" className="py-2 pr-4 font-semibold">When</th>
              <th scope="col" className="py-2 pr-4 font-semibold">Action</th>
              <th scope="col" className="py-2 pr-4 font-semibold">Target</th>
              <th scope="col" className="py-2 font-semibold">Context</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((entry) => (
              <tr key={entry.id} className="border-b border-line/60 last:border-0">
                <td className="py-3 pr-4 text-ink-soft">{formatDate(entry.created_at)}</td>
                <td className="py-3 pr-4 font-mono text-xs text-ink">{entry.action}</td>
                <td className="py-3 pr-4 text-ink-soft">
                  {entry.target_type ? `${entry.target_type}` : "—"}
                </td>
                <td className="py-3 font-mono text-xs text-ink-muted">
                  {entry.context ? JSON.stringify(entry.context) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.total_pages > 1 && (
        <nav aria-label="Pagination" className="mt-6 flex items-center justify-between gap-3">
          <Button
            variant="secondary"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((v) => Math.max(1, v - 1))}
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
            onClick={() => setPage((v) => v + 1)}
          >
            Next
          </Button>
        </nav>
      )}
    </div>
  );
}
