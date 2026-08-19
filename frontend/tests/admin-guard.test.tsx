import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { RequireAuth } from "@/components/require-auth";
import { SessionProvider } from "@/components/session-provider";
import { renderWithProviders, routerReplace, stubFetch } from "./helpers";

function renderGuard(adminOnly = false) {
  return renderWithProviders(
    <SessionProvider>
      <RequireAuth adminOnly={adminOnly}>
        <p>protected content</p>
      </RequireAuth>
    </SessionProvider>,
  );
}

const USER = { id: "1", email: "u@example.com", role: "user", status: "active" };
const ADMIN = { ...USER, role: "admin" };

beforeEach(() => {
  routerReplace.mockClear();
});

describe("RequireAuth", () => {
  it("shows a loading state while the session resolves", () => {
    stubFetch(() => ({ body: { user: null } }));
    renderGuard();
    expect(screen.getByText(/checking your session/i)).toBeInTheDocument();
  });

  it("redirects an anonymous visitor to sign in", async () => {
    stubFetch(() => ({ body: { user: null } }));
    renderGuard();
    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("protected content")).not.toBeInTheDocument();
  });

  it("renders content for a signed-in user", async () => {
    stubFetch(() => ({ body: { user: USER } }));
    renderGuard();
    expect(await screen.findByText("protected content")).toBeInTheDocument();
  });

  it("hides admin content from an ordinary user", async () => {
    stubFetch(() => ({ body: { user: USER } }));
    renderGuard(true);
    expect(await screen.findByText(/restricted to administrators/i)).toBeInTheDocument();
    expect(screen.queryByText("protected content")).not.toBeInTheDocument();
  });

  it("renders admin content for an administrator", async () => {
    stubFetch(() => ({ body: { user: ADMIN } }));
    renderGuard(true);
    expect(await screen.findByText("protected content")).toBeInTheDocument();
  });

  it("states that the server enforces the restriction independently", async () => {
    stubFetch(() => ({ body: { user: USER } }));
    renderGuard(true);
    expect(
      await screen.findByText(/server enforces this independently/i),
    ).toBeInTheDocument();
  });
});
