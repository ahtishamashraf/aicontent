"use client";

import Link from "next/link";
import { useConfig } from "./config-provider";

const LINKS = [
  { href: "/methodology", label: "How it works" },
  { href: "/limitations", label: "Limitations" },
  { href: "/privacy", label: "Privacy" },
  { href: "/terms", label: "Terms" },
];

export function SiteFooter() {
  const { product_name: productName, support_email: supportEmail } = useConfig();

  return (
    <footer className="no-print mt-16 border-t border-line bg-surface">
      <div className="container-page flex flex-col gap-6 py-10 sm:flex-row sm:items-start sm:justify-between">
        <div className="max-w-prose">
          <p className="font-bold text-ink">{productName}</p>
          <p className="mt-2 text-sm text-ink-muted">
            {productName} reports stylistic signals. It does not determine authorship,
            and it should never be the sole basis for a decision about a person.
          </p>
        </div>
        <nav aria-label="Footer">
          <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            {LINKS.map((link) => (
              <li key={link.href}>
                <Link href={link.href} className="text-ink-soft hover:text-brand hover:underline">
                  {link.label}
                </Link>
              </li>
            ))}
            <li>
              <a
                href={`mailto:${supportEmail}`}
                className="text-ink-soft hover:text-brand hover:underline"
              >
                Support
              </a>
            </li>
          </ul>
        </nav>
      </div>
    </footer>
  );
}
