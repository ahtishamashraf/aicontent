"use client";

import type { ReactNode } from "react";

type Tone = "info" | "success" | "warning" | "error";

const TONES: Record<Tone, { wrapper: string; title: string }> = {
  info: { wrapper: "border-brand/30 bg-brand-soft", title: "text-brand" },
  success: { wrapper: "border-success/30 bg-success-soft", title: "text-success" },
  warning: {
    wrapper: "border-band-uncertain/30 bg-band-uncertainSoft",
    title: "text-band-uncertain",
  },
  error: { wrapper: "border-danger/30 bg-danger-soft", title: "text-danger" },
};

/**
 * Errors use role="alert" so they interrupt and are announced immediately;
 * everything else uses a polite status region.
 */
export function Callout({
  tone = "info",
  title,
  children,
  className = "",
}: {
  tone?: Tone;
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  const styles = TONES[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`rounded-card border p-4 ${styles.wrapper} ${className}`}
    >
      {title && <p className={`font-semibold ${styles.title}`}>{title}</p>}
      <div className={`text-sm text-ink-soft ${title ? "mt-1" : ""}`}>{children}</div>
    </div>
  );
}

/** Skeleton placeholder used while content loads. */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-md bg-line/60 ${className}`}
    />
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-card border border-dashed border-line-strong bg-surface px-6 py-14 text-center">
      <h3 className="text-lg font-semibold text-ink">{title}</h3>
      <p className="max-w-prose text-sm text-ink-muted">{description}</p>
      {action}
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <div role="status" className="flex items-center gap-3 text-sm text-ink-muted">
      <span
        aria-hidden="true"
        className="h-4 w-4 animate-spin rounded-full border-2 border-brand border-t-transparent"
      />
      <span>{label}</span>
    </div>
  );
}
