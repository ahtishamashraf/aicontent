import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { LoginForm } from "@/components/auth/login-form";
import { RegisterForm } from "@/components/auth/register-form";
import { SessionProvider } from "@/components/session-provider";
import { renderWithProviders, routerPush, stubFetch } from "./helpers";

beforeEach(() => {
  stubFetch((url) => {
    if (url.includes("/auth/session")) return { body: { user: null } };
    return { body: {} };
  });
});

function renderLogin() {
  return renderWithProviders(
    <SessionProvider>
      <LoginForm />
    </SessionProvider>,
  );
}

describe("LoginForm", () => {
  it("labels both fields", () => {
    renderLogin();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
  });

  it("shows validation errors for empty fields without calling the API", async () => {
    const user = userEvent.setup();
    const fetchSpy = stubFetch(() => ({ body: {} }));
    renderLogin();
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByText(/enter your email address/i)).toBeInTheDocument();
    expect(screen.getByText(/enter your password/i)).toBeInTheDocument();
    const loginCalls = fetchSpy.mock.calls.filter(([url]) =>
      String(url).includes("/auth/login"),
    );
    expect(loginCalls).toHaveLength(0);
  });

  it("associates an error with its field for assistive technology", async () => {
    const user = userEvent.setup();
    renderLogin();
    await user.click(screen.getByRole("button", { name: /sign in/i }));
    const email = await screen.findByLabelText(/email address/i);
    expect(email).toHaveAttribute("aria-invalid", "true");
    expect(email).toHaveAccessibleDescription(/enter your email address/i);
  });

  it("surfaces a generic credential error from the server", async () => {
    const user = userEvent.setup();
    stubFetch((url) => {
      if (url.includes("/auth/session")) return { body: { user: null } };
      return {
        status: 401,
        body: {
          error: {
            code: "invalid_credentials",
            message: "Email or password is incorrect.",
            correlation_id: "abc",
          },
        },
      };
    });
    renderLogin();
    await user.type(screen.getByLabelText(/email address/i), "someone@example.com");
    await user.type(screen.getByLabelText(/password/i), "whatever-password");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /email or password is incorrect/i,
    );
    expect(routerPush).not.toHaveBeenCalled();
  });

  it("navigates on success", async () => {
    const user = userEvent.setup();
    stubFetch((url) => {
      if (url.includes("/auth/login")) {
        return { body: { id: "1", email: "a@example.com", role: "user", status: "active" } };
      }
      if (url.includes("/auth/session")) {
        return {
          body: { user: { id: "1", email: "a@example.com", role: "user", status: "active" } },
        };
      }
      return { body: {} };
    });
    renderLogin();
    await user.type(screen.getByLabelText(/email address/i), "a@example.com");
    await user.type(screen.getByLabelText(/password/i), "a-good-password-here");
    await user.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => expect(routerPush).toHaveBeenCalledWith("/dashboard"));
  });
});

describe("RegisterForm", () => {
  it("rejects a short password before contacting the API", async () => {
    const user = userEvent.setup();
    const fetchSpy = stubFetch(() => ({ body: {} }));
    renderWithProviders(<RegisterForm />);

    await user.type(screen.getByLabelText(/email address/i), "new@example.com");
    await user.type(screen.getByLabelText(/^password/i), "short");
    await user.type(screen.getByLabelText(/confirm password/i), "short");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    // The hint also mentions the length, so assert on the field's error state
    // rather than on text that appears twice by design.
    await waitFor(() => {
      expect(screen.getByLabelText(/^password/i)).toHaveAttribute("aria-invalid", "true");
    });
    expect(screen.getByLabelText(/^password/i)).toHaveAccessibleDescription(
      /use at least 12 characters/i,
    );
    expect(
      fetchSpy.mock.calls.filter(([url]) => String(url).includes("/auth/register")),
    ).toHaveLength(0);
  });

  it("rejects mismatched passwords", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterForm />);
    await user.type(screen.getByLabelText(/email address/i), "new@example.com");
    await user.type(screen.getByLabelText(/^password/i), "a-long-enough-password");
    await user.type(screen.getByLabelText(/confirm password/i), "a-different-password");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/do not match/i)).toBeInTheDocument();
  });

  it("rejects an invalid email address", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegisterForm />);
    await user.type(screen.getByLabelText(/email address/i), "not-an-email");
    await user.type(screen.getByLabelText(/^password/i), "a-long-enough-password");
    await user.type(screen.getByLabelText(/confirm password/i), "a-long-enough-password");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    expect(await screen.findByText(/valid email address/i)).toBeInTheDocument();
  });

  it("shows a neutral acknowledgement on success, not account confirmation", async () => {
    const user = userEvent.setup();
    stubFetch(() => ({ status: 202, body: { message: "ok" } }));
    renderWithProviders(<RegisterForm />);

    await user.type(screen.getByLabelText(/email address/i), "new@example.com");
    await user.type(screen.getByLabelText(/^password/i), "a-long-enough-password");
    await user.type(screen.getByLabelText(/confirm password/i), "a-long-enough-password");
    await user.click(screen.getByRole("button", { name: /create account/i }));

    const notice = await screen.findByText(/check your inbox/i);
    expect(notice).toBeInTheDocument();
    // Must not confirm that the address was previously unregistered.
    expect(screen.queryByText(/account created/i)).not.toBeInTheDocument();
  });
});
