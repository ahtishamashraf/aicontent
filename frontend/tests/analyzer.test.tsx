import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { Analyzer } from "@/components/analyzer";
import { ConfigProvider } from "@/components/config-provider";
import { SessionProvider } from "@/components/session-provider";
import { FALLBACK_CONFIG } from "@/lib/config";
import { makeAnalysis, renderWithProviders, routerPush, stubFetch } from "./helpers";

/** Renders the analyzer inside the providers it depends on. */
function renderAnalyzer() {
  return renderWithProviders(
    <ConfigProvider>
      <SessionProvider>
        <Analyzer />
      </SessionProvider>
    </ConfigProvider>,
  );
}

const LONG_TEXT = "word ".repeat(FALLBACK_CONFIG.min_words + 20);

beforeEach(() => {
  routerPush.mockClear();
  sessionStorage.clear();
  stubFetch((url) => {
    if (url.includes("/config")) return { body: FALLBACK_CONFIG };
    if (url.includes("/auth/session")) return { body: { user: null } };
    return { body: {} };
  });
});

describe("Analyzer", () => {
  it("renders a labelled textarea", async () => {
    renderAnalyzer();
    expect(await screen.findByLabelText(/writing to analyze/i)).toBeInTheDocument();
  });

  it("keeps the submit button disabled while empty", () => {
    renderAnalyzer();
    expect(screen.getByRole("button", { name: /^analyze$/i })).toBeDisabled();
  });

  it("updates the live word, character, and paragraph counts", async () => {
    const user = userEvent.setup();
    renderAnalyzer();
    await user.type(screen.getByLabelText(/writing to analyze/i), "one two\n\nthree");
    await waitFor(() => {
      expect(screen.getByText(/^3$/)).toBeInTheDocument();
    });
    expect(screen.getByText(/2 paragraphs/)).toBeInTheDocument();
  });

  it("says how many more words are needed below the minimum", async () => {
    const user = userEvent.setup();
    renderAnalyzer();
    await user.type(screen.getByLabelText(/writing to analyze/i), "far too short");
    expect(await screen.findByText(/more words needed/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^analyze$/i })).toBeDisabled();
  });

  it("enables submission once the minimum is met", async () => {
    renderAnalyzer();
    const textarea = await screen.findByLabelText(/writing to analyze/i);
    // fireEvent.change rather than typing: 100 words of userEvent is needlessly
    // slow, and a raw `.value` assignment is ignored by React's value tracker.
    fireEvent.change(textarea, { target: { value: LONG_TEXT } });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^analyze$/i })).toBeEnabled();
    });
  });

  it("warns about low reliability between the minimum and the threshold", async () => {
    renderAnalyzer();
    const textarea = await screen.findByLabelText(/writing to analyze/i);
    fireEvent.change(textarea, {
      target: { value: "word ".repeat(FALLBACK_CONFIG.min_words + 5) },
    });
    expect(await screen.findByText(/marked low reliability/i)).toBeInTheDocument();
  });

  it("tells guests their text is discarded", async () => {
    renderAnalyzer();
    expect(await screen.findByText(/discarded after analysis/i)).toBeInTheDocument();
  });

  it("switches between paste and upload modes", async () => {
    const user = userEvent.setup();
    renderAnalyzer();
    await user.click(screen.getByRole("tab", { name: /upload file/i }));
    expect(screen.getByLabelText(/^document$/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/writing to analyze/i)).not.toBeInTheDocument();
  });

  it("rejects a file with a disallowed extension before uploading", async () => {
    const user = userEvent.setup();
    renderAnalyzer();
    await user.click(screen.getByRole("tab", { name: /upload file/i }));
    const input = screen.getByLabelText(/^document$/i);
    // fireEvent rather than user.upload: user-event filters the file against the
    // input's accept attribute and drops it, so the component's own validation —
    // the thing under test — would never run.
    fireEvent.change(input, {
      target: {
        files: [new File(["payload"], "malware.exe", { type: "application/octet-stream" })],
      },
    });
    expect(await screen.findByText(/files are accepted/i)).toBeInTheDocument();
  });

  it("rejects an oversized file client-side", async () => {
    const user = userEvent.setup();
    renderAnalyzer();
    await user.click(screen.getByRole("tab", { name: /upload file/i }));
    const big = new File(["x"], "huge.txt", { type: "text/plain" });
    Object.defineProperty(big, "size", { value: FALLBACK_CONFIG.max_upload_bytes + 1 });
    fireEvent.change(screen.getByLabelText(/^document$/i), { target: { files: [big] } });
    expect(await screen.findByText(/the limit is/i)).toBeInTheDocument();
  });

  it("navigates to the result and stores the guest token on success", async () => {
    const analysis = makeAnalysis({ guest_token: "guest-token-value" });
    stubFetch((url) => {
      if (url.includes("/config")) return { body: FALLBACK_CONFIG };
      if (url.includes("/auth/session")) return { body: { user: null } };
      if (url.includes("/analyses/text")) return { status: 201, body: analysis };
      return { body: {} };
    });

    renderAnalyzer();
    const textarea = await screen.findByLabelText(/writing to analyze/i);
    fireEvent.change(textarea, { target: { value: LONG_TEXT } });

    await waitFor(() => expect(screen.getByRole("button", { name: /^analyze$/i })).toBeEnabled());
    await userEvent.setup().click(screen.getByRole("button", { name: /^analyze$/i }));

    await waitFor(() => {
      expect(routerPush).toHaveBeenCalledWith(`/result/${analysis.id}`);
    });
    expect(sessionStorage.getItem(`originlens.guest.${analysis.id}`)).toBe("guest-token-value");
  });

  it("surfaces a server error without navigating away", async () => {
    stubFetch((url) => {
      if (url.includes("/config")) return { body: FALLBACK_CONFIG };
      if (url.includes("/auth/session")) return { body: { user: null } };
      if (url.includes("/analyses/text")) {
        return {
          status: 429,
          body: {
            error: { code: "rate_limited", message: "Slow down.", correlation_id: "abc" },
          },
        };
      }
      return { body: {} };
    });

    renderAnalyzer();
    const textarea = await screen.findByLabelText(/writing to analyze/i);
    fireEvent.change(textarea, { target: { value: LONG_TEXT } });

    await waitFor(() => expect(screen.getByRole("button", { name: /^analyze$/i })).toBeEnabled());
    await userEvent.setup().click(screen.getByRole("button", { name: /^analyze$/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/too many requests/i);
    expect(routerPush).not.toHaveBeenCalled();
  });
});
