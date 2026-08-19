import type { Metadata } from "next";
import { AccountPanel } from "@/components/account/account-panel";
import { RequireAuth } from "@/components/require-auth";

export const metadata: Metadata = { title: "Account" };

export default function AccountPage() {
  return (
    <RequireAuth>
      <div className="container-page max-w-3xl py-10 sm:py-14">
        <h1 className="text-3xl font-bold text-ink">Account settings</h1>
        <div className="mt-8">
          <AccountPanel />
        </div>
      </div>
    </RequireAuth>
  );
}
