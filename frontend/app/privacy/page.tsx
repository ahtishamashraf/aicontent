import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy",
  description: "What OriginLens stores, for how long, and what it never records.",
};

export default function PrivacyPage() {
  return (
    <div className="container-page max-w-prose py-10 sm:py-14">
      <h1 className="text-3xl font-bold text-ink">Privacy</h1>
      <p className="mt-4 text-lg leading-8 text-ink-soft">
        Submitted writing is sensitive. This page describes how it is handled in concrete
        terms rather than in general reassurances.
      </p>

      <h2 className="mt-10 text-xl font-bold text-ink">Your text</h2>
      <ul className="mt-3 list-disc space-y-2 pl-5 leading-7 text-ink-soft">
        <li>Guest submissions are analysed and then discarded. Nothing is retained.</li>
        <li>
          Signed-in users may opt to keep a copy. When you do, it is encrypted at rest with
          AES-256-GCM and can be deleted at any time from your history.
        </li>
        <li>
          Text is never written to application logs, error traces, analytics, queue messages,
          or the administrator console. The background worker reads it from the database by
          reference, so it never passes through the job queue.
        </li>
        <li>Nothing is sent to an external model provider. Analysis runs on our own machines.</li>
      </ul>

      <h2 className="mt-10 text-xl font-bold text-ink">Guest results</h2>
      <p className="mt-3 leading-7 text-ink-soft">
        A guest result is addressed by a random token held only by your browser. The server
        stores just a hash of it, so we cannot reconstruct your link. Guest results and their
        tokens expire automatically.
      </p>

      <h2 className="mt-10 text-xl font-bold text-ink">Accounts</h2>
      <ul className="mt-3 list-disc space-y-2 pl-5 leading-7 text-ink-soft">
        <li>Passwords are stored as Argon2id hashes. We never see or store the password.</li>
        <li>
          Sessions use random opaque tokens; the server keeps only a hash, so a database
          disclosure does not yield usable sessions.
        </li>
        <li>
          Verification and password-reset links are single-use, expiring, and also stored as
          hashes.
        </li>
        <li>
          Deleting your account removes your analyses, retained text, sessions, tokens, and
          feedback.
        </li>
      </ul>

      <h2 className="mt-10 text-xl font-bold text-ink">Rate limiting without tracking</h2>
      <p className="mt-3 leading-7 text-ink-soft">
        Abuse prevention needs to tell clients apart, but it does not need to know who they
        are. We store a keyed hash of the client identifier rather than an IP address. The
        hash is not reversible, and rotating the server-side key invalidates every stored
        identifier.
      </p>

      <h2 className="mt-10 text-xl font-bold text-ink">Retention</h2>
      <p className="mt-3 leading-7 text-ink-soft">
        Guest results and expired sessions are removed on a schedule. Retention periods are
        configured by the operator of this deployment and are enforced by a background sweep,
        not merely by policy.
      </p>
    </div>
  );
}
