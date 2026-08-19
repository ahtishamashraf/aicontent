import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResultActions } from "@/components/result/result-actions";
import { makeAnalysis, renderWithProviders } from "./helpers";

beforeEach(() => {
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock-url");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  window.print = vi.fn();
});

describe("ResultActions", () => {
  it("offers export, print, and copy actions", () => {
    renderWithProviders(<ResultActions analysis={makeAnalysis()} />);
    expect(screen.getByRole("button", { name: /download json/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /print report/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /copy link/i })).toBeInTheDocument();
  });

  it("builds a downloadable blob from data already on the page", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ResultActions analysis={makeAnalysis()} />);
    await user.click(screen.getByRole("button", { name: /download json/i }));
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
  });

  it("triggers the browser print dialog", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ResultActions analysis={makeAnalysis()} />);
    await user.click(screen.getByRole("button", { name: /print report/i }));
    expect(window.print).toHaveBeenCalledTimes(1);
  });

  it("is hidden from printed output", () => {
    const { container } = renderWithProviders(<ResultActions analysis={makeAnalysis()} />);
    expect(container.firstElementChild?.className).toContain("no-print");
  });

  it("announces a copied link politely", async () => {
    const user = userEvent.setup();
    // navigator.clipboard is a getter-only property in jsdom, so it has to be
    // redefined rather than assigned.
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    renderWithProviders(<ResultActions analysis={makeAnalysis()} />);
    await user.click(screen.getByRole("button", { name: /copy link/i }));

    // The button relabels itself and a polite live region announces the change.
    expect(
      await screen.findByRole("button", { name: /link copied/i }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/link copied to clipboard/i)).toBeInTheDocument();
  });
});
