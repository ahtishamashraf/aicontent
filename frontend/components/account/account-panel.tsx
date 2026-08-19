"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useSession } from "@/components/session-provider";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { TextField } from "@/components/ui/field";
import { Callout } from "@/components/ui/feedback";
import { MIN_PASSWORD_LENGTH } from "@/components/auth/register-form";

export function AccountPanel() {
  const { user, refresh } = useSession();
  const router = useRouter();

  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordDone, setPasswordDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  if (!user) return null;

  function validate(): boolean {
    const errors: Record<string, string> = {};
    if (!current) errors["current"] = "Enter your current password.";
    if (next.length < MIN_PASSWORD_LENGTH) {
      errors["next"] = `Use at least ${MIN_PASSWORD_LENGTH} characters.`;
    }
    if (next !== confirm) errors["confirm"] = "The two passwords do not match.";
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function changePassword(event: React.FormEvent) {
    event.preventDefault();
    if (!validate()) return;

    setBusy(true);
    setPasswordError(null);
    try {
      await api.post("/api/v1/auth/password/change", {
        current_password: current,
        new_password: next,
      });
      setPasswordDone(true);
      setCurrent("");
      setNext("");
      setConfirm("");
      await refresh();
    } catch (caught) {
      setPasswordError(
        caught instanceof ApiError ? caught.message : "The password could not be changed.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function deleteAccount() {
    setBusy(true);
    setDeleteError(null);
    try {
      await api.delete("/api/v1/auth/account");
      await refresh();
      router.push("/");
    } catch (caught) {
      setDeleteError(
        caught instanceof ApiError ? caught.message : "The account could not be deleted.",
      );
      setBusy(false);
      setConfirmDelete(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="profile-heading" className="card p-6">
        <h2 id="profile-heading" className="text-lg font-bold text-ink">
          Profile
        </h2>
        <dl className="mt-4 grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="font-medium text-ink-muted">Email</dt>
            <dd className="break-words text-ink">{user.email}</dd>
          </div>
          <div>
            <dt className="font-medium text-ink-muted">Role</dt>
            <dd className="text-ink">{user.role === "admin" ? "Administrator" : "User"}</dd>
          </div>
          <div>
            <dt className="font-medium text-ink-muted">Member since</dt>
            <dd className="text-ink">{formatDate(user.created_at)}</dd>
          </div>
          <div>
            <dt className="font-medium text-ink-muted">Email confirmed</dt>
            <dd className="text-ink">
              {user.email_verified_at ? formatDate(user.email_verified_at) : "Not confirmed"}
            </dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby="password-heading" className="card p-6">
        <h2 id="password-heading" className="text-lg font-bold text-ink">
          Change password
        </h2>
        <p className="mt-1 text-sm text-ink-muted">
          Changing your password signs out every other session.
        </p>

        {passwordDone && (
          <Callout tone="success" className="mt-4">
            Your password has been changed.
          </Callout>
        )}
        {passwordError && (
          <Callout tone="error" className="mt-4">
            {passwordError}
          </Callout>
        )}

        <form onSubmit={changePassword} noValidate className="mt-4 flex max-w-md flex-col gap-4">
          <TextField
            label="Current password"
            type="password"
            autoComplete="current-password"
            required
            value={current}
            error={fieldErrors["current"] ?? null}
            onChange={(event) => setCurrent(event.target.value)}
          />
          <TextField
            label="New password"
            type="password"
            autoComplete="new-password"
            required
            value={next}
            error={fieldErrors["next"] ?? null}
            onChange={(event) => setNext(event.target.value)}
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
          <Button type="submit" loading={busy} loadingText="Saving…" className="self-start">
            Change password
          </Button>
        </form>
      </section>

      <section aria-labelledby="danger-heading" className="card border-danger/30 p-6">
        <h2 id="danger-heading" className="text-lg font-bold text-danger">
          Delete account
        </h2>
        <p className="mt-1 max-w-prose text-sm text-ink-soft">
          Removes your account, every analysis, all retained text, your sessions, and your
          feedback. This cannot be undone.
        </p>
        {deleteError && (
          <Callout tone="error" className="mt-4">
            {deleteError}
          </Callout>
        )}
        <Button variant="danger" onClick={() => setConfirmDelete(true)} className="mt-4">
          Delete my account
        </Button>
      </section>

      <ConfirmDialog
        open={confirmDelete}
        title="Delete your account?"
        description="Your account and every associated record are removed permanently. This cannot be undone."
        confirmLabel="Delete permanently"
        destructive
        busy={busy}
        onConfirm={deleteAccount}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  );
}
