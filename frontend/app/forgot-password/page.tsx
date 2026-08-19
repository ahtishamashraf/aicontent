import type { Metadata } from "next";
import { Suspense } from "react";
import { AuthShell } from "@/components/auth/auth-shell";
import { ForgotPasswordForm } from "@/components/auth/token-action-form";

export const metadata: Metadata = { title: "Reset your password" };

export default function Page() {
  return (
    <AuthShell title="Reset your password" description="We will email a link if the address is registered.">
      <Suspense fallback={null}>
        <ForgotPasswordForm />
      </Suspense>
    </AuthShell>
  );
}
