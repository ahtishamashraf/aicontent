import Link from "next/link";
import type { ReactNode } from "react";

export function AuthShell({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="container-page flex max-w-md flex-col py-12 sm:py-16">
      <h1 className="text-2xl font-bold text-ink">{title}</h1>
      <p className="mt-2 text-sm text-ink-soft">{description}</p>
      <div className="card mt-6 p-6">{children}</div>
      {footer && <div className="mt-5 text-center text-sm text-ink-soft">{footer}</div>}
      <p className="mt-8 text-center text-xs text-ink-muted">
        By continuing you agree to the{" "}
        <Link href="/terms" className="underline hover:text-brand">
          terms
        </Link>{" "}
        and{" "}
        <Link href="/privacy" className="underline hover:text-brand">
          privacy notice
        </Link>
        .
      </p>
    </div>
  );
}
