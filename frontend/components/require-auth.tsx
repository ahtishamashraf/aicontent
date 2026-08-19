"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useSession } from "./session-provider";
import { Skeleton } from "./ui/feedback";

/**
 * Client-side gate.
 *
 * This is a convenience so a signed-out visitor sees a sign-in prompt instead of
 * an error. It is *not* the access control: every protected route re-checks the
 * session and role server-side on each request.
 */
export function RequireAuth({
  children,
  adminOnly = false,
}: {
  children: ReactNode;
  adminOnly?: boolean;
}) {
  const { user, loading } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!user) router.replace("/login");
  }, [user, loading, router]);

  if (loading) {
    return (
      <div className="container-page max-w-4xl py-12">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="mt-6 h-48 w-full" />
        <p className="sr-only">Checking your session…</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="container-page max-w-2xl py-16">
        <h1 className="text-2xl font-bold text-ink">Sign in required</h1>
        <p className="mt-3 text-ink-soft">Redirecting you to the sign-in page…</p>
      </div>
    );
  }

  if (adminOnly && user.role !== "admin") {
    return (
      <div className="container-page max-w-2xl py-16">
        <h1 className="text-2xl font-bold text-ink">Not available</h1>
        <p className="mt-3 text-ink-soft">
          This area is restricted to administrators. The server enforces this
          independently of what the interface shows.
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
