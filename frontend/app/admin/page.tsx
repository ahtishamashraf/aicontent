import type { Metadata } from "next";
import { AdminConsole } from "@/components/admin/admin-console";
import { RequireAuth } from "@/components/require-auth";

export const metadata: Metadata = { title: "Administration" };

export default function AdminPage() {
  return (
    <RequireAuth adminOnly>
      <div className="container-page max-w-6xl py-10 sm:py-14">
        <h1 className="text-3xl font-bold text-ink">Administration</h1>
        <p className="mt-2 max-w-prose text-ink-soft">
          Account management, service health, and the audit trail. Submitted text is not
          reachable from this console.
        </p>
        <div className="mt-8">
          <AdminConsole />
        </div>
      </div>
    </RequireAuth>
  );
}
