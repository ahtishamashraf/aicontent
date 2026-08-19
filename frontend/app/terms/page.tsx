import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terms",
  description: "Acceptable use and the limits of what OriginLens results mean.",
};

export default function TermsPage() {
  return (
    <div className="container-page max-w-prose py-10 sm:py-14">
      <h1 className="text-3xl font-bold text-ink">Terms of use</h1>

      <h2 className="mt-10 text-xl font-bold text-ink">What this service provides</h2>
      <p className="mt-3 leading-7 text-ink-soft">
        OriginLens returns an estimate of whether writing carries patterns associated with
        machine generation, together with a reliability assessment. It is an analysis aid. It
        is not an authorship determination, a forensic finding, or evidence.
      </p>

      <h2 className="mt-10 text-xl font-bold text-ink">No warranty of accuracy</h2>
      <p className="mt-3 leading-7 text-ink-soft">
        Results can be wrong in both directions. We make no accuracy guarantee, and we publish
        no headline accuracy figure because we have not measured one on a dataset that would
        support the claim. See{" "}
        <Link href="/limitations" className="font-semibold text-brand underline">
          Limitations
        </Link>{" "}
        before relying on any result.
      </p>

      <h2 className="mt-10 text-xl font-bold text-ink">Acceptable use</h2>
      <ul className="mt-3 list-disc space-y-2 pl-5 leading-7 text-ink-soft">
        <li>Submit only text you have the right to submit.</li>
        <li>
          Do not use a result as the sole basis for a decision that affects someone —
          disciplinary action, grading, hiring, or contract termination.
        </li>
        <li>Do not attempt to overwhelm, probe, or circumvent the service&rsquo;s limits.</li>
        <li>Do not present a result as proof of authorship to anyone.</li>
      </ul>

      <h2 className="mt-10 text-xl font-bold text-ink">Accounts</h2>
      <p className="mt-3 leading-7 text-ink-soft">
        You are responsible for keeping your credentials secure. Accounts that abuse the
        service may be suspended; a suspended account is told that it has been suspended.
      </p>

      <h2 className="mt-10 text-xl font-bold text-ink">Availability</h2>
      <p className="mt-3 leading-7 text-ink-soft">
        The service is provided as-is, without a guarantee of availability. When analysis is
        unavailable you will be told so explicitly — you will never be shown a fabricated
        result in place of a real one.
      </p>
    </div>
  );
}
