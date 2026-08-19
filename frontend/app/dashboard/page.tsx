import type { Metadata } from "next";
import Link from "next/link";
import { HistoryTable } from "@/components/dashboard/history-table";
import { RequireAuth } from "@/components/require-auth";

export const metadata: Metadata = { title: "My analyses" };

export default function DashboardPage() {
  return (
    <RequireAuth>
      <div className="container-page max-w-5xl py-10 sm:py-14">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-ink">My analyses</h1>
            <p className="mt-2 max-w-prose text-ink-soft">
              Everything you have analysed while signed in. Deleting an entry removes its
              result and any text you chose to keep.
            </p>
          </div>
          <Link
            href="/analyze"
            className="inline-flex min-h-11 shrink-0 items-center rounded-lg bg-brand px-5 text-sm font-semibold text-white hover:bg-brand-hover"
          >
            New analysis
          </Link>
        </div>
        <div className="mt-8">
          <HistoryTable />
        </div>
        <div className="mt-12 border-t border-line pt-8">
          <Link href="/account" className="text-sm font-semibold text-brand hover:underline">
            Account settings
          </Link>
        </div>
      </div>
    </RequireAuth>
  );
}
