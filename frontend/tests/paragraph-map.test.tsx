import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ParagraphMap } from "@/components/result/paragraph-map";
import { BANDS, makeSegment, renderWithProviders } from "./helpers";

describe("ParagraphMap", () => {
  it("lists every paragraph in document order", () => {
    const segments = [
      makeSegment({ id: "p-000", index: 0 }),
      makeSegment({ id: "p-001", index: 1 }),
      makeSegment({ id: "p-002", index: 2 }),
    ];
    renderWithProviders(<ParagraphMap segments={segments} bands={BANDS} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons[0]).toHaveTextContent("Paragraph 1");
    expect(buttons[2]).toHaveTextContent("Paragraph 3");
  });

  it("reports how many paragraphs could be scored", () => {
    const segments = [
      makeSegment({ id: "p-000", index: 0, public_score: 40 }),
      makeSegment({ id: "p-001", index: 1, public_score: null, too_short: true }),
    ];
    renderWithProviders(<ParagraphMap segments={segments} bands={BANDS} />);
    expect(screen.getByText(/1 of 2 paragraphs/i)).toBeInTheDocument();
  });

  it("shows 'Not scored' rather than a number for a short paragraph", () => {
    const segments = [
      makeSegment({ id: "p-000", index: 0, public_score: null, label: null, too_short: true }),
    ];
    renderWithProviders(<ParagraphMap segments={segments} bands={BANDS} />);
    expect(screen.getByText("Not scored")).toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("expands a paragraph on click and collapses it again", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <ParagraphMap segments={[makeSegment({ label: "Likely AI-patterned" })]} bands={BANDS} />,
    );
    const toggle = screen.getByRole("button", { name: /paragraph 1/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Band:/)).toBeInTheDocument();

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("is operable with the keyboard alone", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ParagraphMap segments={[makeSegment()]} bands={BANDS} />);
    await user.tab();
    const toggle = screen.getByRole("button", { name: /paragraph 1/i });
    expect(toggle).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("explains why a short paragraph carries no number", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <ParagraphMap
        segments={[makeSegment({ public_score: null, too_short: true, word_count: 3 })]}
        bands={BANDS}
      />,
    );
    await user.click(screen.getByRole("button", { name: /paragraph 1/i }));
    expect(screen.getByText(/too short to score on its own/i)).toBeInTheDocument();
  });

  it("marks a paragraph scored with borrowed context", () => {
    renderWithProviders(
      <ParagraphMap
        segments={[makeSegment({ grouped_with_context: true, word_count: 20 })]}
        bands={BANDS}
      />,
    );
    expect(screen.getByText(/scored with surrounding context/i)).toBeInTheDocument();
  });

  it("renders nothing when there are no segments", () => {
    const { container } = renderWithProviders(<ParagraphMap segments={[]} bands={BANDS} />);
    expect(container).toBeEmptyDOMElement();
  });
});
