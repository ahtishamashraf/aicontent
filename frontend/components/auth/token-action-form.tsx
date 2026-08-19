"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";
import { Callout, Spinner } from "@/components/ui/feedback";
import { MIN_PASSWORD_LENGTH } from "./register-form";

/** Consumes an email-verification token from the query string on mount. */
export function VerifyEmailForm() {
  const params = useSearchParams();
  const token = params.get("token");
  const [state, setState] = useState<"idle" | "working" | "done" | "error">("idle");
  const [message, setMessage] = useState("");
  const attempted = useRef(false);

  useEffect(() => {
    if (!token || attempted.current) return;
    attempted.current = true;
    setState("working");
    api
      .post<{ message: string }>("/api/v1/auth/verify", { token })
      .then((response) => {
        setState("done");
        setMessage(response.message);
      })
      .catch((caught: unknown) => {
        setState("error");
        setMessage(
          caught instanceof ApiError
            ? caught.message
            : "This confirmation link could not be used.",
        );
      });
  }, [token]);

  if (!token) {
    return (
      <Callout tone="error" title="Missing confirmation token">
        Open the link exactly as it appears in your email.
      </Callout>
    );
  }
  if (state === "working" || state === "idle") {
    return <Spinner label="Confirming your address…" />;
  }
  if (state === "error") {
    return (
      <Callout tone="error" title="Could not confirm">
        {message}
      </Callout>
    );
  }
  return (
    <Callout tone="success" title="Address confirmed">
      {message}{" "}
      <Link href="/login" className="font-semibold underline">
        Sign in
      </Link>
    </Callout>
  );
}

/** Requests a password reset link. Always reports the same acknowledgement. */
export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await api.post<{ message: string }>(
        "/api/v1/auth/password/forgot",
        { email: email.trim() },
      );
      setSent(response.message);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Request failed.");
    } finally {
      setBusy(false);
    }
  }

  if (sent) {
    return (
      <Callout tone="success" title="Request received">
        {sent}
      </Callout>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {error && <Callout tone="error">{error}</Callout>}
      <TextField
        label="Email address"
        type="email"
        autoComplete="email"
        required
        value={email}
        onChange={(event) => setEmail(event.target.value)}
      />
      <Button type="submit" loading={busy} loadingText="Sending…" className="w-full">
        Send reset link
      </Button>
    </form>
  );
}

/** Consumes a reset token and sets a new password. */
export function ResetPasswordForm() {
  const params = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  function validate(): boolean {
    const next: Record<string, string> = {};
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
      await api.post("/api/v1/auth/password/reset", { token, password });
      setDone(true);
    } catch (caught) {
      setError(
        caught instanceof ApiError ? caught.message : "The password could not be changed.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return (
      <Callout tone="error" title="Missing reset token">
        Open the link exactly as it appears in your email.
      </Callout>
    );
  }

  if (done) {
    return (
      <Callout tone="success" title="Password changed">
        Every existing session was signed out.{" "}
        <Link href="/login" className="font-semibold underline">
          Sign in with your new password
        </Link>
      </Callout>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
      {error && <Callout tone="error">{error}</Callout>}
      <TextField
        label="New password"
        type="password"
        autoComplete="new-password"
        required
        hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
        value={password}
        error={fieldErrors["password"] ?? null}
        onChange={(event) => setPassword(event.target.value)}
      />
      <TextField
        label="Confirm new password"
        type="password"
        autoComplete="new-password"
        required
        value={confirm}
        error={fieldErrors["confirm"] ?? null}
        onChange={(event) => setConfirm(event.target.value)}
      />
      <Button type="submit" loading={busy} loadingText="Saving…" className="w-full">
        Set new password
      </Button>
    </form>
  );
}
