"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useSession } from "@/components/session-provider";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";
import { Callout } from "@/components/ui/feedback";

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { refresh } = useSession();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  function validate(): boolean {
    const next: Record<string, string> = {};
    if (!email.trim()) next["email"] = "Enter your email address.";
    if (!password) next["password"] = "Enter your password.";
    setFieldErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!validate()) return;

    setBusy(true);
    setError(null);
    try {
      await api.post("/api/v1/auth/login", { email: email.trim(), password });
      await refresh();
      router.push(params.get("next") ?? "/dashboard");
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "Sign in failed. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {error && (
        <Callout tone="error" title="Could not sign in">
          {error}
        </Callout>
      )}

      <TextField
        label="Email address"
        type="email"
        autoComplete="email"
        required
        value={email}
        error={fieldErrors["email"] ?? null}
        onChange={(event) => setEmail(event.target.value)}
      />
      <TextField
        label="Password"
        type="password"
        autoComplete="current-password"
        required
        value={password}
        error={fieldErrors["password"] ?? null}
        onChange={(event) => setPassword(event.target.value)}
      />

      <div className="flex justify-end">
        <Link href="/forgot-password" className="text-sm font-medium text-brand hover:underline">
          Forgot your password?
        </Link>
      </div>

      <Button type="submit" loading={busy} loadingText="Signing in…" className="w-full">
        Sign in
      </Button>
    </form>
  );
}
