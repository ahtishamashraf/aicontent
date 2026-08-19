"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { useConfig } from "./config-provider";
import { useSession } from "./session-provider";
import { Button } from "./ui/button";

const PUBLIC_LINKS = [
  { href: "/analyze", label: "Analyze" },
  { href: "/methodology", label: "How it works" },
  { href: "/limitations", label: "Limitations" },
];

export function SiteNav() {
  const { product_name: productName } = useConfig();
  const { user, loading, signOut } = useSession();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [menuPath, setMenuPath] = useState(pathname);

  // Navigating closes the menu. Adjusting state during render is React's
  // recommended pattern here — an effect would render the open menu first and
  // then close it, producing a visible flash.
  if (pathname !== menuPath) {
    setMenuPath(pathname);
    setOpen(false);
  }

  const links = [
    ...PUBLIC_LINKS,
    ...(user ? [{ href: "/dashboard", label: "My analyses" }] : []),
    ...(user?.role === "admin" ? [{ href: "/admin", label: "Admin" }] : []),
  ];

  async function handleSignOut() {
    await signOut();
    router.push("/");
  }

  return (
    <header className="no-print sticky top-0 z-40 border-b border-line bg-surface/95 backdrop-blur">
      <nav aria-label="Main" className="container-page flex h-16 items-center gap-4">
        <Link
          href="/"
          className="flex shrink-0 items-center gap-2 rounded font-bold text-ink"
        >
          <span
            aria-hidden="true"
            className="grid h-8 w-8 place-items-center rounded-lg bg-brand text-sm font-black text-white"
          >
            OL
          </span>
          <span className="hidden sm:inline">{productName}</span>
        </Link>

        <ul className="ml-auto hidden items-center gap-1 md:flex">
          {links.map((link) => {
            const active = pathname === link.href;
            return (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  className={[
                    "rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    active
                      ? "bg-brand-soft text-brand"
                      : "text-ink-soft hover:bg-surface-sunken hover:text-ink",
                  ].join(" ")}
                >
                  {link.label}
                </Link>
              </li>
            );
          })}
        </ul>

        <div className="ml-auto hidden items-center gap-2 md:ml-0 md:flex">
          {loading ? (
            <span className="h-9 w-24 animate-pulse rounded-md bg-line/60" aria-hidden="true" />
          ) : user ? (
            <Button variant="secondary" size="sm" onClick={handleSignOut}>
              Sign out
            </Button>
          ) : (
            <>
              <Link
                href="/login"
                className="rounded-md px-3 py-2 text-sm font-medium text-ink-soft hover:text-ink"
              >
                Sign in
              </Link>
              <Link
                href="/register"
                className="inline-flex min-h-9 items-center rounded-lg bg-brand px-4 text-sm font-semibold text-white hover:bg-brand-hover"
              >
                Create account
              </Link>
            </>
          )}
        </div>

        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls="mobile-menu"
          className="ml-auto inline-flex h-10 w-10 items-center justify-center rounded-md border border-line-strong text-ink md:hidden"
        >
          <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
          <span aria-hidden="true" className="text-lg leading-none">
            {open ? "✕" : "☰"}
          </span>
        </button>
      </nav>

      {open && (
        <div id="mobile-menu" className="border-t border-line bg-surface md:hidden">
          <ul className="container-page flex flex-col py-2">
            {links.map((link) => (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={pathname === link.href ? "page" : undefined}
                  className="block rounded-md px-3 py-3 text-sm font-medium text-ink-soft hover:bg-surface-sunken"
                >
                  {link.label}
                </Link>
              </li>
            ))}
            <li className="mt-2 border-t border-line pt-2">
              {user ? (
                <Button variant="secondary" size="sm" onClick={handleSignOut} className="w-full">
                  Sign out
                </Button>
              ) : (
                <div className="flex flex-col gap-2">
                  <Link
                    href="/login"
                    className="rounded-md px-3 py-3 text-sm font-medium text-ink-soft"
                  >
                    Sign in
                  </Link>
                  <Link
                    href="/register"
                    className="inline-flex min-h-11 items-center justify-center rounded-lg bg-brand px-4 text-sm font-semibold text-white"
                  >
                    Create account
                  </Link>
                </div>
              )}
            </li>
          </ul>
        </div>
      )}
    </header>
  );
}
