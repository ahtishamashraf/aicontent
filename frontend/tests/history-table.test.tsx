import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { ConfigProvider } from "@/components/config-provider";
import { HistoryTable } from "@/components/dashboard/history-table";
import { FALLBACK_CONFIG } from "@/lib/config";
import type { AnalysisSummary } from "@/lib/types";
import { renderWithProviders, stubFetch } from "./helpers";

function summary(overrides: Partial<AnalysisSummary> = {}): AnalysisSummary {
  return {
    id: "aaaaaaaa-0000-0000-0000-000000000001",
    status: "completed",
    source: "text",
    source_filename: null,
    created_at: "2026-03-01T10:00:00Z",
    label: "Likely human-patterned",
    public_score: 22,
    reliability: "normal",
    word_count: 400,
    ...overrides,
  };
}

function page(items: AnalysisSummary[], overrides: Record<string, unknown> = {}) {
  return {
    items,
    total: items.length,
    page: 1,
    page_size: 10,
    total_pages: 1,
    ...overrides,
  };
}

function renderTable() {
  return renderWithProviders(
    <ConfigProvider>
      <HistoryTable />
    </ConfigProvider>,
  );
}

beforeEach(() => {
  stubFetch((url) => {
    if (url.includes("/config")) return { body: FALLBACK_CONFIG };
    return { body: page([summary()]) };
  });
});

describe("HistoryTable", () => {
  it("shows a loading state before data arrives", () => {
    renderTable();
    expect(screen.getByText(/loading your analyses/i)).toBeInTheDocument();
  });

  it("renders rows once loaded", async () => {
    renderTable();
    expect(await screen.findAllByText("Likely human-patterned")).not.toHaveLength(0);
    expect(screen.getAllByText("22").length).toBeGreaterThan(0);
  });

  it("shows an empty state when there is no history", async () => {
    stubFetch((url) => {
      if (url.includes("/config")) return { body: FALLBACK_CONFIG };
      return { body: page([]) };
    });
    renderTable();
    expect(await screen.findByText(/no analyses yet/i)).toBeInTheDocument();
  });

  it("shows a different empty state when filters exclude everything", async () => {
    const user = userEvent.setup();
    stubFetch((url) => {
      if (url.includes("/config")) return { body: FALLBACK_CONFIG };
      if (url.includes("status=failed")) return { body: page([]) };
      return { body: page([summary()]) };
    });
    renderTable();
    await screen.findAllByText("Likely human-patterned");
    await user.selectOptions(screen.getByLabelText(/status/i), "failed");
    expect(await screen.findByText(/nothing matches those filters/i)).toBeInTheDocument();
  });

  it("surfaces a server error", async () => {
    stubFetch((url) => {
      if (url.includes("/config")) return { body: FALLBACK_CONFIG };
      return {
        status: 500,
        body: { error: { code: "internal_error", message: "Boom.", correlation_id: "x" } },
      };
    });
    renderTable();
    expect(await screen.findByRole("alert")).toHaveTextContent("Boom.");
  });

  it("sends the chosen filters to the API", async () => {
    const user = userEvent.setup();
    const fetchSpy = stubFetch((url) => {
      if (url.includes("/config")) return { body: FALLBACK_CONFIG };
      return { body: page([summary()]) };
    });
    renderTable();
    await screen.findAllByText("Likely human-patterned");

    await user.selectOptions(screen.getByLabelText(/source/i), "document");
    await waitFor(() => {
      const urls = fetchSpy.mock.calls.map(([url]) => String(url));
      expect(urls.some((url) => url.includes("source=document"))).toBe(true);
    });
  });

  it("renders pagination only when there is more than one page", async () => {
    stubFetch((url) => {
      if (url.includes("/config")) return { body: FALLBACK_CONFIG };
      return { body: page([summary()], { total: 30, total_pages: 3 }) };
    });
    renderTable();
    const nav = await screen.findByRole("navigation", { name: /pagination/i });
    expect(within(nav).getByText(/page 1 of 3/i)).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: /previous/i })).toBeDisabled();
  });

  it("asks for confirmation before deleting and does not delete on cancel", async () => {
    const user = userEvent.setup();
    const fetchSpy = stubFetch((url) => {
      if (url.includes("/config")) return { body: FALLBACK_CONFIG };
      return { body: page([summary()]) };
    });
    renderTable();
    await screen.findAllByText("Likely human-patterned");

    await user.click(screen.getAllByRole("button", { name: /^delete$/i })[0]!);
    expect(await screen.findByRole("alertdialog")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /cancel/i }));
    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    });
    const deletes = fetchSpy.mock.calls.filter(([, init]) => init?.method === "DELETE");
    expect(deletes).toHaveLength(0);
  });

  it("issues the delete request when confirmed", async () => {
    const user = userEvent.setup();
    const fetchSpy = stubFetch((url) => {
      if (url.includes("/config")) return { body: FALLBACK_CONFIG };
      return { body: page([summary()]) };
    });
    renderTable();
    await screen.findAllByText("Likely human-patterned");

    await user.click(screen.getAllByRole("button", { name: /^delete$/i })[0]!);

    // Scope to the dialog: the row button and the dialog's confirm share a name.
    const dialog = await screen.findByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: /^delete$/i }));

    await waitFor(() => {
      const deletes = fetchSpy.mock.calls.filter(([, init]) => init?.method === "DELETE");
      expect(deletes.length).toBeGreaterThan(0);
    });
  });

  it("renders a dash instead of zero for an unscored analysis", async () => {
    stubFetch((url) => {
      if (url.includes("/config")) return { body: FALLBACK_CONFIG };
      return {
        body: page([
          summary({ public_score: null, label: "Insufficient text", reliability: "insufficient" }),
        ]),
      };
    });
    renderTable();
    expect(await screen.findAllByText("—")).not.toHaveLength(0);
  });
});
