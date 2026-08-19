import type { Metadata } from "next";
import { Suspense } from "react";
import { AuthShell } from "@/components/auth/auth-shell";
import { VerifyEmailForm } from "@/components/auth/token-action-form";

export const metadata: Metadata = { title: "Confirm your email" };

export default function Page() {
  return (
    <AuthShell title="Confirm your email" description="Confirming the address on your account.">
      <Suspense fallback={null}>
        <VerifyEmailForm />
      </Suspense>
    </AuthShell>
  );
}
