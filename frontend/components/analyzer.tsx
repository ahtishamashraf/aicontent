"use client";

import { useRouter } from "next/navigation";
import { useCallback, useId, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { countParagraphs, countWords, formatBytes, messageForError } from "@/lib/format";
import type { Analysis } from "@/lib/types";
import { useConfig } from "./config-provider";
import { useSession } from "./session-provider";
import { Button } from "./ui/button";
import { Callout } from "./ui/feedback";

type Mode = "text" | "document";
type Phase = "idle" | "submitting" | "done" | "error";

/**
 * Guest results are addressed by a token that is never persisted server-side in
 * readable form. Keeping it in sessionStorage means a reload can still open the
 * result, and closing the tab discards it.
 */
export const GUEST_TOKEN_PREFIX = "originlens.guest.";

export function rememberGuestToken(id: string, token: string): void {
  try {
    sessionStorage.setItem(`${GUEST_TOKEN_PREFIX}${id}`, token);
  } catch {
    // Private browsing can refuse storage; the result is still shown now.
  }
}

export function recallGuestToken(id: string): string | null {
  try {
    return sessionStorage.getItem(`${GUEST_TOKEN_PREFIX}${id}`);
  } catch {
    return null;
  }
}

export function Analyzer() {
  const config = useConfig();
  const { user } = useSession();
  const router = useRouter();

  const [mode, setMode] = useState<Mode>("text");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [storeText, setStoreText] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const textAreaId = useId();
  const fileInputId = useId();

  const counts = useMemo(
    () => ({
      words: countWords(text),
      characters: text.length,
      paragraphs: countParagraphs(text),
    }),
    [text],
  );

  const tooShort = counts.words > 0 && counts.words < config.min_words;
  const tooLong =
    counts.words > config.max_words || counts.characters > config.max_characters;
  const lowReliability =
    counts.words >= config.min_words && counts.words < config.low_reliability_words;

  const canSubmit =
    phase !== "submitting" &&
    (mode === "text"
      ? counts.words >= config.min_words && !tooLong
      : file !== null && fileError === null);

  const validateFile = useCallback(
    (candidate: File): string | null => {
      const name = candidate.name.toLowerCase();
      const extension = name.slice(name.lastIndexOf("."));
      if (!config.allowed_extensions.includes(extension)) {
        return `Only ${config.allowed_extensions.join(", ")} files are accepted.`;
      }
      if (candidate.size > config.max_upload_bytes) {
        return `That file is ${formatBytes(candidate.size)}. The limit is ${formatBytes(
          config.max_upload_bytes,
        )}.`;
      }
      if (candidate.size === 0) return "That file is empty.";
      return null;
    },
    [config.allowed_extensions, config.max_upload_bytes],
  );

  function handleFileChange(selected: File | null) {
    setFile(selected);
    setFileError(selected ? validateFile(selected) : null);
    setError(null);
  }

  async function handleSubmit() {
    setPhase("submitting");
    setError(null);

    try {
      let analysis: Analysis;
      if (mode === "text") {
        analysis = await api.post<Analysis>("/api/v1/analyses/text", {
          text,
          store_original_text: user ? storeText : false,
        });
      } else {
        if (!file) return;
        const formData = new FormData();
        formData.append("file", file);
        analysis = await api.upload<Analysis>(
          "/api/v1/analyses/document",
          formData,
          user && storeText ? { store_original_text: true } : undefined,
        );
      }

      if (analysis.guest_token) {
        rememberGuestToken(analysis.id, analysis.guest_token);
      }
      setPhase("done");
      router.push(`/result/${analysis.id}`);
    } catch (caught) {
      setPhase("error");
      if (caught instanceof ApiError) {
        setError(messageForError(caught.code, caught.message));
      } else {
        setError("Something went wrong. Please try again.");
      }
    }
  }

  return (
    <section aria-labelledby="analyzer-heading" className="card p-5 sm:p-7">
      <h2 id="analyzer-heading" className="text-xl font-bold text-ink">
        Analyze writing
      </h2>
      <p className="mt-1 text-sm text-ink-muted">
        Paste at least {config.min_words} words, or upload a document. English only.
      </p>

      <div
        role="tablist"
        aria-label="Submission type"
        className="mt-5 inline-flex rounded-lg border border-line-strong bg-surface-sunken p-1"
      >
        {(["text", "document"] as const).map((value) => (
          <button
            key={value}
            role="tab"
            type="button"
            aria-selected={mode === value}
            aria-controls={value === "text" ? "panel-text" : "panel-document"}
            onClick={() => {
              setMode(value);
              setError(null);
            }}
            className={[
              "min-h-9 rounded-md px-4 text-sm font-semibold transition-colors",
              mode === value
                ? "bg-surface text-ink shadow-sm"
                : "text-ink-muted hover:text-ink",
            ].join(" ")}
          >
            {value === "text" ? "Paste text" : "Upload file"}
          </button>
        ))}
      </div>

      {mode === "text" ? (
        <div id="panel-text" role="tabpanel" className="mt-5">
          <label htmlFor={textAreaId} className="text-sm font-semibold text-ink">
            Writing to analyze
          </label>
          <textarea
            id={textAreaId}
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={12}
            maxLength={config.max_characters}
            aria-describedby="analyzer-counts"
            placeholder="Paste the writing you want to analyze…"
            className="mt-2 w-full resize-y rounded-lg border border-line-strong bg-surface p-4 leading-7 text-ink placeholder:text-ink-muted/70 hover:border-ink-muted"
          />

          <p
            id="analyzer-counts"
            aria-live="polite"
            className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-muted"
          >
            <span>
              <strong className="tabular-nums text-ink">{counts.words.toLocaleString()}</strong>{" "}
              {counts.words === 1 ? "word" : "words"}
            </span>
            <span className="tabular-nums">
              {counts.characters.toLocaleString()} / {config.max_characters.toLocaleString()}{" "}
              characters
            </span>
            <span className="tabular-nums">{counts.paragraphs} paragraphs</span>
          </p>

          {tooShort && (
            <p className="mt-3 text-sm text-ink-soft">
              {config.min_words - counts.words} more words needed before analysis can run.
            </p>
          )}
          {lowReliability && (
            <Callout tone="warning" className="mt-3">
              Below {config.low_reliability_words} words the result will be marked low
              reliability. Longer text gives the analyser more to work with.
            </Callout>
          )}
          {tooLong && (
            <Callout tone="error" className="mt-3">
              This submission is over the limit of {config.max_words.toLocaleString()} words
              or {config.max_characters.toLocaleString()} characters.
            </Callout>
          )}
        </div>
      ) : (
        <div id="panel-document" role="tabpanel" className="mt-5">
          <label htmlFor={fileInputId} className="text-sm font-semibold text-ink">
            Document
          </label>
          <p className="mt-1 text-sm text-ink-muted">
            {config.allowed_extensions.join(", ")} up to{" "}
            {formatBytes(config.max_upload_bytes)}. Scanned PDFs are not supported.
          </p>
          <input
            ref={fileInputRef}
            id={fileInputId}
            type="file"
            accept={config.allowed_extensions.join(",")}
            aria-invalid={fileError ? true : undefined}
            aria-describedby={fileError ? "file-error" : undefined}
            onChange={(event) => handleFileChange(event.target.files?.[0] ?? null)}
            className="mt-3 block w-full cursor-pointer rounded-lg border border-line-strong bg-surface p-3 text-sm text-ink file:mr-4 file:min-h-9 file:rounded-md file:border-0 file:bg-brand-soft file:px-4 file:text-sm file:font-semibold file:text-brand hover:file:bg-brand-soft/70"
          />
          {file && !fileError && (
            <p className="mt-2 text-sm text-ink-muted">
              Selected: <strong className="text-ink">{file.name}</strong> (
              {formatBytes(file.size)})
            </p>
          )}
          {fileError && (
            <p id="file-error" className="mt-2 text-sm font-medium text-danger">
              {fileError}
            </p>
          )}
        </div>
      )}

      {user && (
        <div className="mt-5 flex items-start gap-3 rounded-lg bg-surface-sunken p-4">
          <input
            id="store-text"
            type="checkbox"
            checked={storeText}
            onChange={(event) => setStoreText(event.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 rounded border-line-strong text-brand"
          />
          <label htmlFor="store-text" className="text-sm text-ink-soft">
            <span className="font-semibold text-ink">Keep a copy of this text</span>
            <span className="mt-0.5 block">
              Stored encrypted so you can re-read it later. Leave unticked and the text is
              discarded once the analysis finishes.
            </span>
          </label>
        </div>
      )}

      {!user && (
        <p className="mt-5 text-sm text-ink-muted">
          Submitting as a guest. Your text is discarded after analysis, and the result link
          expires in {config.guest_retention_hours} hours.
        </p>
      )}

      {error && (
        <Callout tone="error" title="Analysis failed" className="mt-5">
          {error}
        </Callout>
      )}

      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-ink-muted">Results are estimates, not proof of authorship.</p>
        <Button
          onClick={handleSubmit}
          disabled={!canSubmit}
          loading={phase === "submitting"}
          loadingText="Analyzing…"
          className="w-full sm:w-auto"
        >
          Analyze
        </Button>
      </div>
    </section>
  );
}
