"use client";

import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";
import { useId } from "react";

interface BaseProps {
  label: string;
  hint?: string;
  error?: string | null;
  required?: boolean;
}

/**
 * Every field owns a real <label>, and its hint and error are wired through
 * aria-describedby so a screen reader announces them with the control rather
 * than leaving them as orphaned text.
 */
function useFieldIds(error?: string | null, hint?: string) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return { id, hintId, errorId, describedBy };
}

function FieldShell({
  label,
  hint,
  error,
  required,
  id,
  hintId,
  errorId,
  children,
}: BaseProps & {
  id: string;
  hintId?: string;
  errorId?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-semibold text-ink">
        {label}
        {required && (
          <span className="ml-1 text-danger" aria-hidden="true">
            *
          </span>
        )}
        {required && <span className="sr-only"> (required)</span>}
      </label>
      {hint && (
        <p id={hintId} className="text-sm text-ink-muted">
          {hint}
        </p>
      )}
      {children}
      {error && (
        <p id={errorId} className="text-sm font-medium text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

const CONTROL_CLASSES =
  "w-full rounded-lg border bg-surface px-3 py-2.5 text-ink placeholder:text-ink-muted/70 " +
  "transition-colors disabled:cursor-not-allowed disabled:bg-surface-sunken disabled:text-ink-muted";

export function TextField({
  label,
  hint,
  error,
  required,
  className = "",
  ...rest
}: BaseProps & InputHTMLAttributes<HTMLInputElement>) {
  const { id, hintId, errorId, describedBy } = useFieldIds(error, hint);
  return (
    <FieldShell
      label={label}
      hint={hint}
      error={error}
      required={required}
      id={id}
      hintId={hintId}
      errorId={errorId}
    >
      <input
        id={id}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={[
          CONTROL_CLASSES,
          error ? "border-danger" : "border-line-strong hover:border-ink-muted",
          className,
        ].join(" ")}
        {...rest}
      />
    </FieldShell>
  );
}

export function TextAreaField({
  label,
  hint,
  error,
  required,
  className = "",
  ...rest
}: BaseProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const { id, hintId, errorId, describedBy } = useFieldIds(error, hint);
  return (
    <FieldShell
      label={label}
      hint={hint}
      error={error}
      required={required}
      id={id}
      hintId={hintId}
      errorId={errorId}
    >
      <textarea
        id={id}
        required={required}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={[
          CONTROL_CLASSES,
          "resize-y leading-7",
          error ? "border-danger" : "border-line-strong hover:border-ink-muted",
          className,
        ].join(" ")}
        {...rest}
      />
    </FieldShell>
  );
}
