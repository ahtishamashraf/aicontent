import Link from "next/link";
import { Analyzer } from "@/components/analyzer";

const POINTS = [
  {
    title: "Signals, not verdicts",
    body: "Every result states a band, a reliability level, and the reasons behind it — not a bare percentage dressed up as certainty.",
  },
  {
    title: "Reasons you can inspect",
    body: "Paragraph-level scores, window agreement, and neutral text statistics are all shown, so you can see what the result rests on.",
  },
  {
    title: "Private by default",
    body: "Guest submissions are discarded once analysed. Nothing is sent to an external model provider, and no submitted text is written to logs.",
  },
];

export default function HomePage() {
  return (
    <>
      <section className="container-page grid gap-10 py-12 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] lg:py-20">
        <div className="self-center">
          <p className="inline-flex items-center rounded-pill bg-brand-soft px-3 py-1 text-sm font-semibold text-brand">
            Private by design · Honest by default
          </p>
          <h1 className="mt-5 text-4xl font-black leading-tight text-ink sm:text-5xl">
            See the signals.
            <br />
            Keep the context.
          </h1>
          <p className="mt-5 max-w-prose text-lg leading-8 text-ink-soft">
            OriginLens analyses writing for patterns associated with AI generation, and
            reports how much weight that finding can bear. It will not tell you who wrote
            something, and it is built not to pretend otherwise.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/methodology"
              className="inline-flex min-h-11 items-center rounded-lg bg-ink px-5 text-sm font-semibold text-white hover:bg-ink-soft"
            >
              How it works
            </Link>
            <Link
              href="/limitations"
              className="inline-flex min-h-11 items-center rounded-lg border border-line-strong bg-surface px-5 text-sm font-semibold text-ink hover:bg-surface-sunken"
            >
              Read the limitations
            </Link>
          </div>
        </div>

        <Analyzer />
      </section>

      <section aria-labelledby="principles" className="border-t border-line bg-surface">
        <div className="container-page py-14">
          <h2 id="principles" className="text-2xl font-bold text-ink">
            What this tool does, and what it will not do
          </h2>
          <ul className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {POINTS.map((point) => (
              <li key={point.title} className="rounded-card border border-line p-5">
                <h3 className="font-bold text-ink">{point.title}</h3>
                <p className="mt-2 text-sm leading-6 text-ink-soft">{point.body}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </>
  );
}
