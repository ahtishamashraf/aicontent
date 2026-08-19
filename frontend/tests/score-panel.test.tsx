import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScorePanel } from "@/components/result/score-panel";
import { BANDS, makeAnalysis, renderWithProviders } from "./helpers";

describe("ScorePanel", () => {
  it("shows the score and its band label", () => {
    renderWithProviders(<ScorePanel analysis={makeAnalysis()} bands={BANDS} />);
    expect(screen.getByText("78")).toBeInTheDocument();
    // The label appears twice by design: as the headline and in the band legend.
    expect(screen.getAllByText("Likely AI-patterned").length).toBeGreaterThanOrEqual(1);
  });

  it("tints the panel with the band the score actually falls in", () => {
    const { container } = renderWithProviders(
      <ScorePanel
        analysis={makeAnalysis({ public_score: 50, label: "Uncertain or mixed signals" })}
        bands={BANDS}
      />,
    );
    const section = container.querySelector("section");
    // Regression guard for the "uncertain contains ai" substring bug.
    expect(section?.className).toContain("band-uncertain");
    expect(section?.className).not.toContain("band-aiSoft");
  });

  it("states the reliability in words, not as a percentage", () => {
    renderWithProviders(<ScorePanel analysis={makeAnalysis()} bands={BANDS} />);
    expect(screen.getByText("Normal reliability")).toBeInTheDocument();
    expect(screen.queryByText(/\d+% confiden/i)).not.toBeInTheDocument();
  });

  it("lists the reasons behind a reduced reliability", () => {
    const analysis = makeAnalysis({
      reliability: "low",
      reliability_reasons: ["Only 100 words were analysed."],
    });
    renderWithProviders(<ScorePanel analysis={analysis} bands={BANDS} />);
    expect(screen.getByText("Why this reliability")).toBeInTheDocument();
    expect(screen.getByText("Only 100 words were analysed.")).toBeInTheDocument();
  });

  it("explains a missing score instead of rendering zero", () => {
    const analysis = makeAnalysis({
      public_score: null,
      raw_model_score: null,
      label: "Insufficient text",
      reliability: "insufficient",
    });
    renderWithProviders(<ScorePanel analysis={analysis} bands={BANDS} />);
    expect(screen.getByText("No score")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
    expect(screen.getByText("Insufficient text")).toBeInTheDocument();
  });

  it("gives the score meter an accessible text description", () => {
    renderWithProviders(<ScorePanel analysis={makeAnalysis()} bands={BANDS} />);
    expect(
      screen.getByRole("img", { name: /score 78 out of 100/i }),
    ).toBeInTheDocument();
  });

  it("labels every band in words so colour is not the only signal", () => {
    renderWithProviders(<ScorePanel analysis={makeAnalysis()} bands={BANDS} />);
    for (const band of BANDS) {
      expect(screen.getAllByText(band.label).length).toBeGreaterThan(0);
    }
  });
});

describe("ScorePanel headings", () => {
  it("uses a heading name distinct from the page heading", () => {
    renderWithProviders(<ScorePanel analysis={makeAnalysis()} bands={BANDS} />);
    expect(
      screen.getByRole("heading", { name: /overall ai signal score/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /^analysis result$/i })).toBeNull();
  });
});
