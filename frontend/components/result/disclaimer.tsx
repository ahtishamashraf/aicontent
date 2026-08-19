/**
 * The disclaimer travels with the result itself — on screen, in print, and in
 * the JSON export — so a screenshot or printout cannot separate the number from
 * what it does and does not mean.
 */
export function ResultDisclaimer({ disclaimers }: { disclaimers: string[] }) {
  return (
    <section
      aria-labelledby="disclaimer-heading"
      data-testid="result-disclaimer"
      className="print-disclaimer rounded-card border border-band-uncertain/40 bg-band-uncertainSoft p-5"
    >
      <h2 id="disclaimer-heading" className="font-bold text-band-uncertain">
        Interpret this responsibly
      </h2>
      <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-ink-soft">
        {disclaimers.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </section>
  );
}
