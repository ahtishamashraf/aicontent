"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";
import { Callout } from "@/components/ui/feedback";

export const MIN_PASSWORD_LENGTH = 12;

export function RegisterForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  function validate(): boolean {
    const next: Record<string, string> = {};
    if (!email.includes("@")) next["email"] = "Enter a valid email address.";
    if (password.length < MIN_PASSWORD_LENGTH) {
      next["password"] = `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
    }
    if (password !== confirm) next["confirm"] = "The two passwords do not match.";
    setFieldErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!validate()) return;

    setBusy(true);
    setError(null);
    try {
      await api.post("/api/v1/auth/register", { email: email.trim(), password });
      setDone(true);
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "Registration failed. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <Callout tone="success" title="Check your inbox">
        If that address can receive mail, a confirmation link is on its way. The link expires
        in 24 hours.
      </Callout>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {error && (
        <Callout tone="error" title="Could not create the account">
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
        autoComplete="new-password"
        required
        hint={`At least ${MIN_PASSWORD_LENGTH} characters. A memorable phrase beats a short complicated string.`}
        value={password}
        error={fieldErrors["password"] ?? null}
        onChange={(event) => setPassword(event.target.value)}
      />
      <TextField
        label="Confirm password"
        type="password"
        autoComplete="new-password"
        required
        value={confirm}
        error={fieldErrors["confirm"] ?? null}
        onChange={(event) => setConfirm(event.target.value)}
      />

      <Button type="submit" loading={busy} loadingText="Creating account…" className="w-full">
        Create account
      </Button>
    </form>
  );
}
