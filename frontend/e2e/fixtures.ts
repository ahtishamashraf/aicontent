import { expect, type Page } from "@playwright/test";

/**
 * Sample prose used across the E2E suite.
 *
 * This is written for the test suite. No real user writing appears in any
 * fixture, and none ever should.
 */
export const ENGLISH_SAMPLE = [
  "The committee reviewed the revised proposal during the March session, and several",
  "members raised concerns about the delivery timeline. In particular, the assumption",
  "that procurement would complete before the summer recess struck two of them as",
  "optimistic. The chair agreed to circulate a revised schedule before the next meeting.",
  "",
  "A second matter concerned staffing levels across the department. Two vacancies have",
  "gone unfilled since January, and the resulting workload has fallen on a team smaller",
  "than the original plan assumed. Recruitment is under way, but suitable candidates",
  "remain scarce in this specialism, and the salary band has not moved in three years.",
  "",
  "Finally, the group discussed the archive migration. Progress has been slow because",
  "the source records are inconsistent: some are catalogued by accession number, others",
  "by donor, and a handful by nothing at all. The archivist proposed a triage approach,",
  "tackling the catalogued material first and setting aside the remainder for later.",
].join("\n");

export const SHORT_SAMPLE = "Only a handful of words, nowhere near the minimum.";

export const FRENCH_SAMPLE = [
  "Le comite a examine la proposition revisee avec beaucoup d attention pendant la",
  "session de mars et plusieurs membres ont exprime des inquietudes au sujet du",
  "calendrier de livraison propose par la direction generale du service concerne.",
  "La question du recrutement reste egalement ouverte car deux postes sont vacants",
  "depuis le mois de janvier dernier et la charge de travail repose desormais sur une",
  "equipe beaucoup plus reduite que prevu initialement par le plan de la direction.",
  "Le president a donc accepte de faire circuler un nouveau calendrier avant la",
  "prochaine reunion du comite directeur charge de ce dossier particulier.",
].join(" ");

export function uniqueEmail(prefix = "e2e"): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 10_000)}@example.com`;
}

export const PASSWORD = "e2e-correct-horse-battery-staple";

/** Submit text through the analyzer and land on the result page. */
export async function analyzeText(page: Page, text: string): Promise<void> {
  await page.goto("/analyze");
  await page.getByLabel("Writing to analyze").fill(text);
  await page.getByRole("button", { name: "Analyze", exact: true }).click();
}

/** Assert the document is not wider than the viewport. */
export async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    return {
      scrollWidth: doc.scrollWidth,
      clientWidth: doc.clientWidth,
    };
  });
  // Allow a single pixel for sub-pixel rounding.
  expect(
    overflow.scrollWidth,
    `page scrolls horizontally: ${overflow.scrollWidth} > ${overflow.clientWidth}`,
  ).toBeLessThanOrEqual(overflow.clientWidth + 1);
}

/** Collect uncaught console errors for the lifetime of a test. */
export function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}
