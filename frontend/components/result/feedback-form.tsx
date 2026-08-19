"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/feedback";
import { TextAreaField } from "@/components/ui/field";

type Verdict = "agree" | "disagree" | "unsure";

const OPTIONS: { value: Verdict; label: string }[] = [
  { value: "agree", label: "Matches my expectation" },
  { value: "disagree", label: "Does not match" },
  { value: "unsure", label: "Not sure" },
];

/** Feedback is about the result. It is never a place to resubmit the document. */
export function FeedbackForm({
  analysisId,
  guestToken,
}: {
  analysisId: string;
  guestToken?: string | null;
}) {
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [comment, setComment] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (!verdict) return;
    setState("sending");
    setError(null);
    try {
      await api.post(
        `/api/v1/analyses/${analysisId}/feedback`,
        { verdict, comment: comment.trim() || null },
        guestToken ? { token: guestToken } : undefined,
      );
      setState("sent");
    } catch (caught) {
      setState("error");
      setError(
        caught instanceof ApiError ? caught.message : "Feedback could not be sent.",
      );
    }
  }

  if (state === "sent") {
    return (
      <Callout tone="success" title="Thank you">
        Your feedback was recorded. It helps us understand where the analyser is weak.
      </Callout>
    );
  }

  return (
    <section aria-labelledby="feedback-heading" className="no-print card p-5 sm:p-7">
      <h2 id="feedback-heading" className="text-lg font-bold text-ink">
        Was this result useful?
      </h2>
      <p className="mt-1 text-sm text-ink-muted">
        Tell us about the result, not the document. Do not paste the text again here.
      </p>

      <fieldset className="mt-4">
        <legend className="sr-only">Your assessment of this result</legend>
        <div className="flex flex-wrap gap-2">
          {OPTIONS.map((option) => (
            <label
              key={option.value}
              className={[
                "cursor-pointer rounded-lg border px-4 py-2 text-sm font-medium transition-colors",
                verdict === option.value
                  ? "border-brand bg-brand-soft text-brand"
                  : "border-line-strong text-ink-soft hover:bg-surface-sunken",
              ].join(" ")}
            >
              <input
                type="radio"
                name="verdict"
                value={option.value}
                checked={verdict === option.value}
                onChange={() => setVerdict(option.value)}
                className="sr-only"
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="mt-4">
        <TextAreaField
          label="Anything else? (optional)"
          hint="Maximum 2000 characters."
          rows={3}
          maxLength={2000}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
        />
      </div>

      {error && (
        <Callout tone="error" className="mt-4">
          {error}
        </Callout>
      )}

      <Button
        onClick={submit}
        disabled={!verdict}
        loading={state === "sending"}
        loadingText="Sending…"
        className="mt-4"
      >
        Send feedback
      </Button>
    </section>
  );
}
