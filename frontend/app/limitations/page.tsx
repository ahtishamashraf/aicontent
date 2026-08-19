import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Limitations",
  description: "Where OriginLens is unreliable, and what it must never be used for.",
};

const FAILURES = [
  {
    title: "Non-native English writing",
    body: "Writers using a second language often produce more regular sentence structures and a narrower vocabulary. Those are the same surface features associated with generated text. This is a well-documented source of false positives, and it falls hardest on the people least able to contest the result.",
  },
  {
    title: "Formulaic and technical writing",
    body: "Legal boilerplate, lab reports, standards documents, and academic abstracts are conventionally repetitive. That regularity is the genre working correctly, not a sign of generation.",
  },
  {
    title: "Edited and collaborative text",
    body: "Human writing revised with a grammar checker, or generated text a person has substantially rewritten, sits between the two categories the analyser was built to separate.",
  },
  {
    title: "Translated text",
    body: "Machine translation flattens style in ways that resemble generation, whoever wrote the original.",
  },
  {
    title: "Deliberate evasion",
    body: "Paraphrasing tools, homoglyph substitution, and inserted invisible characters can all move a score. We report the ones we can detect, but absence of a warning is not proof of absence.",
  },
  {
    title: "Short text",
    body: "Below the minimum word count nothing is scored at all. Between the minimum and the reliability threshold, treat the result as a weak hint.",
  },
];

export default function LimitationsPage() {
  return (
    <div className="container-page max-w-prose py-10 sm:py-14">
      <h1 className="text-3xl font-bold text-ink">Limitations</h1>
      <p className="mt-4 text-lg leading-8 text-ink-soft">
        Detectors of this kind are unreliable in ways that matter. This page exists so you can
        weigh a result properly, and it is deliberately not buried.
      </p>

      <div className="mt-8 rounded-card border border-danger/30 bg-danger-soft p-5">
        <h2 className="font-bold text-danger">Never use this as the sole basis for a decision</h2>
        <p className="mt-2 text-sm leading-6 text-ink-soft">
          Do not use an OriginLens score on its own to accuse someone of misconduct, fail a
          student, reject a candidate, or terminate a contract. A score is one weak signal.
          Consequential decisions about people need corroborating evidence, an opportunity for
          the person to respond, and human judgement.
        </p>
      </div>

      <h2 className="mt-12 text-xl font-bold text-ink">Where it goes wrong</h2>
      <ul className="mt-6 flex flex-col gap-6">
        {FAILURES.map((item) => (
          <li key={item.title}>
            <h3 className="font-bold text-ink">{item.title}</h3>
            <p className="mt-2 leading-7 text-ink-soft">{item.body}</p>
          </li>
        ))}
      </ul>

      <h2 className="mt-12 text-xl font-bold text-ink">What the bands actually mean</h2>
      <p className="mt-3 leading-7 text-ink-soft">
        &ldquo;Likely AI-patterned&rdquo; means the text carries surface features that resemble
        machine-generated writing in the analyser&rsquo;s training distribution. It does not mean
        the text was generated. &ldquo;Likely human-patterned&rdquo; means the reverse, and is
        equally not a clearance. &ldquo;Uncertain or mixed signals&rdquo; is a real answer, not a
        failure — it is what an honest analyser returns when the evidence does not separate.
      </p>

      <h2 className="mt-12 text-xl font-bold text-ink">No accuracy claim</h2>
      <p className="mt-3 leading-7 text-ink-soft">
        We publish no accuracy figure, because we have not measured one on a dataset large or
        representative enough to support the claim. The evaluation tooling in this repository
        withholds metrics below documented sample thresholds for the same reason. Any vendor
        quoting a single headline accuracy number for AI text detection is describing their
        test set, not your document.
      </p>
    </div>
  );
}
