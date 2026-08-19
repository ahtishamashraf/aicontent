import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResultDisclaimer } from "@/components/result/disclaimer";
import { renderWithProviders } from "./helpers";

const DISCLAIMERS = [
  "This score is an estimate of stylistic patterns, not proof of authorship.",
  "The analyser is validated for English only.",
];

describe("ResultDisclaimer", () => {
  it("renders every disclaimer", () => {
    renderWithProviders(<ResultDisclaimer disclaimers={DISCLAIMERS} />);
    for (const line of DISCLAIMERS) {
      expect(screen.getByText(line)).toBeInTheDocument();
    }
  });

  it("is a labelled landmark so it is reachable by assistive technology", () => {
    renderWithProviders(<ResultDisclaimer disclaimers={DISCLAIMERS} />);
    expect(
      screen.getByRole("heading", { name: /interpret this responsibly/i }),
    ).toBeInTheDocument();
  });

  it("is not marked no-print, so it survives on a printed result", () => {
    renderWithProviders(<ResultDisclaimer disclaimers={DISCLAIMERS} />);
    const section = screen.getByTestId("result-disclaimer");
    expect(section.className).not.toContain("no-print");
    expect(section.className).toContain("print-disclaimer");
  });
});
