"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /** Shows a spinner, disables interaction, and announces the busy state. */
  loading?: boolean;
  loadingText?: string;
  children: ReactNode;
}

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-brand text-white hover:bg-brand-hover active:bg-brand-hover " +
    "disabled:bg-line-strong disabled:text-ink-muted",
  secondary:
    "border border-line-strong bg-surface text-ink hover:bg-surface-sunken " +
    "active:bg-line/40 disabled:text-ink-muted disabled:bg-surface-sunken",
  ghost:
    "text-brand hover:bg-brand-soft active:bg-brand-soft/70 disabled:text-ink-muted",
  danger:
    "bg-danger text-white hover:brightness-95 active:brightness-90 " +
    "disabled:bg-line-strong disabled:text-ink-muted",
};

const SIZES: Record<Size, string> = {
  sm: "min-h-9 px-3 text-sm",
  md: "min-h-11 px-5 text-sm",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  loadingText,
  disabled,
  children,
  className = "",
  type = "button",
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;
  return (
    <button
      type={type}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={[
        "inline-flex items-center justify-center gap-2 rounded-lg font-semibold",
        "transition-colors disabled:cursor-not-allowed",
        VARIANTS[variant],
        SIZES[size],
        className,
      ].join(" ")}
      {...rest}
    >
      {loading && (
        <span
          aria-hidden="true"
          className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent"
        />
      )}
      <span>{loading && loadingText ? loadingText : children}</span>
    </button>
  );
}
