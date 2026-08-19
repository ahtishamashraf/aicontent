import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "How it works",
  description: "What OriginLens measures, how it segments text, and how scores are produced.",
};

const STEPS = [
  {
    title: "1. Normalize, without rewriting",
    body: "Your text is kept exactly as submitted for display. A separate copy is prepared for analysis: line endings are canonicalised and invisible formatting characters removed, but words, punctuation, casing, and paragraph boundaries are untouched. Invisible characters, mixed scripts, homoglyphs, and unusual whitespace are reported to you as integrity notes rather than silently corrected.",
  },
  {
    title: "2. Check the language",
    body: "Language detection runs locally — your text is never sent to a third party for it. The analyser is validated for English only. If English confidence falls below the documented threshold, you get 'Unsupported language' instead of a number that would mean nothing.",
  },
  {
    title: "3. Check there is enough to work with",
    body: "Below the minimum word count the analyser returns 'Insufficient text' and stops before doing any expensive work. Between the minimum and the reliability threshold, analysis runs but the result is marked low reliability, because short samples genuinely are less reliable.",
  },
  {
    title: "4. Split into overlapping windows",
    body: "The text is divided into overlapping windows measured in model tokens, never by character count — a character slice can cut a word in half and change what the model sees. Each window is scored separately.",
  },
  {
    title: "5. Combine the windows",
    body: "Window scores are combined with each window weighted by how many tokens it contains, so a short trailing window does not count as much as a full one. The spread between window scores is also measured: when sections of a document disagree strongly, reliability drops and the result is moved into the uncertain band, because a genuinely mixed document should not be presented as a confident verdict.",
  },
  {
    title: "6. Map to a public score",
    body: "The model's raw output is stored separately from the score you see. The public score is currently the raw output multiplied by one hundred — an identity mapping. It is deliberately not called a probability, because calling it one would require a validated calibration dataset that this project does not have.",
  },
];

export default function MethodologyPage() {
  return (
    <div className="container-page max-w-prose py-10 sm:py-14">
      <h1 className="text-3xl font-bold text-ink">How it works</h1>
      <p className="mt-4 text-lg leading-8 text-ink-soft">
        OriginLens looks for stylistic patterns statistically associated with machine-generated
        text. It cannot observe who typed something, and no amount of statistics turns a
        pattern into proof.
      </p>

      <ol className="mt-10 flex flex-col gap-8">
        {STEPS.map((step) => (
          <li key={step.title}>
            <h2 className="text-lg font-bold text-ink">{step.title}</h2>
            <p className="mt-2 leading-7 text-ink-soft">{step.body}</p>
          </li>
        ))}
      </ol>

      <h2 className="mt-12 text-xl font-bold text-ink">The statistics we show you</h2>
      <p className="mt-3 leading-7 text-ink-soft">
        Alongside the score, every result carries neutral measurements: sentence and paragraph
        length variation, lexical variety, repeated phrases and sentence openings, punctuation
        and function-word distribution, transition-phrase density, and how similar adjacent
        sentences are in shape.
      </p>
      <p className="mt-3 leading-7 text-ink-soft">
        These are context, not evidence. They are <strong>not</strong> combined into the score.
        Assigning them invented weights and presenting the total as a measurement would be
        pseudo-science, so we do not do it.
      </p>

      <h2 className="mt-12 text-xl font-bold text-ink">Calibration, stated honestly</h2>
      <p className="mt-3 leading-7 text-ink-soft">
        A calibrated score would mean that documents scoring 70 are machine-generated about 70%
        of the time. Establishing that requires a large, representative, labelled dataset and a
        published reliability diagram. This project ships neither, so the calibration is the
        identity mapping and its version string says <code className="rounded bg-surface-sunken px-1">identity</code> so
        nobody can mistake it for something it is not.
      </p>
    </div>
  );
}
