import type { Metadata } from "next";
import { Suspense } from "react";
import { AuthShell } from "@/components/auth/auth-shell";
import { ResetPasswordForm } from "@/components/auth/token-action-form";

export const metadata: Metadata = { title: "Choose a new password" };

export default function Page() {
  return (
    <AuthShell title="Choose a new password" description="Setting a new password signs out every existing session.">
      <Suspense fallback={null}>
        <ResetPasswordForm />
      </Suspense>
    </AuthShell>
  );
}
