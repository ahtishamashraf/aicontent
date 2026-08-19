import { expect, test } from "@playwright/test";
import { ENGLISH_SAMPLE, PASSWORD, analyzeText, uniqueEmail } from "./fixtures";

/**
 * Registration requires confirming an emailed link. In a disposable test stack
 * that mail lands in Mailpit; when `E2E_MAILPIT_URL` is set the token is read
 * from there, otherwise these tests are skipped rather than pretending to pass.
 */
const MAILPIT = process.env.E2E_MAILPIT_URL;

async function verificationTokenFor(email: string): Promise<string | null> {
  if (!MAILPIT) return null;
  const search = await fetch(`${MAILPIT}/api/v1/search?query=to:${encodeURIComponent(email)}`);
  if (!search.ok) return null;
  const results = (await search.json()) as { messages?: { ID: string }[] };
  const id = results.messages?.[0]?.ID;
  if (!id) return null;

  const message = await fetch(`${MAILPIT}/api/v1/message/${id}`);
  const body = (await message.json()) as { Text?: string };
  return body.Text?.match(/token=([\w-]+)/)?.[1] ?? null;
}

test.describe("Registered user", () => {
  test.skip(!MAILPIT, "E2E_MAILPIT_URL is not set, so email confirmation cannot be completed");

  test("registers, verifies, analyses, sees history, and deletes", async ({ page }) => {
    const email = uniqueEmail("user");

    await page.goto("/register");
    await page.getByLabel("Email address").fill(email);
    await page.getByLabel(/^password/i).fill(PASSWORD);
    await page.getByLabel(/confirm password/i).fill(PASSWORD);
    await page.getByRole("button", { name: /create account/i }).click();
    await expect(page.getByText(/check your inbox/i)).toBeVisible();

    const token = await verificationTokenFor(email);
    expect(token, "no verification token found in Mailpit").toBeTruthy();

    await page.goto(`/verify?token=${token}`);
    await expect(page.getByText(/address confirmed/i)).toBeVisible();

    await page.goto("/login");
    await page.getByLabel("Email address").fill(email);
    await page.getByLabel(/^password/i).fill(PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page).toHaveURL(/\/dashboard/);

    await analyzeText(page, ENGLISH_SAMPLE);
    await expect(page).toHaveURL(/\/result\//);

    await page.goto("/dashboard");
    await expect(page.getByRole("link", { name: "View" }).first()).toBeVisible();

    await page.getByRole("button", { name: /^delete$/i }).first().click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: /^delete$/i }).click();

    await expect(page.getByText(/no analyses yet/i)).toBeVisible();
  });

  test("one user cannot open another user's analysis", async ({ page, context }) => {
    const ownerEmail = uniqueEmail("owner");
    const intruderEmail = uniqueEmail("intruder");

    for (const email of [ownerEmail, intruderEmail]) {
      await page.goto("/register");
      await page.getByLabel("Email address").fill(email);
      await page.getByLabel(/^password/i).fill(PASSWORD);
      await page.getByLabel(/confirm password/i).fill(PASSWORD);
      await page.getByRole("button", { name: /create account/i }).click();
      await expect(page.getByText(/check your inbox/i)).toBeVisible();

      const token = await verificationTokenFor(email);
      expect(token).toBeTruthy();
      await page.goto(`/verify?token=${token}`);
    }

    await page.goto("/login");
    await page.getByLabel("Email address").fill(ownerEmail);
    await page.getByLabel(/^password/i).fill(PASSWORD);
    await page.getByRole("button", { name: /sign in/i }).click();
    await analyzeText(page, ENGLISH_SAMPLE);
    await expect(page).toHaveURL(/\/result\//);
    const ownedUrl = page.url();

    const intruder = await context.browser()!.newContext();
    const intruderPage = await intruder.newPage();
    await intruderPage.goto("/login");
    await intruderPage.getByLabel("Email address").fill(intruderEmail);
    await intruderPage.getByLabel(/^password/i).fill(PASSWORD);
    await intruderPage.getByRole("button", { name: /sign in/i }).click();

    await intruderPage.goto(ownedUrl);
    await expect(
      intruderPage.getByRole("heading", { name: /not available/i }),
    ).toBeVisible();
    await intruder.close();
  });
});

test.describe("Authorization boundaries", () => {
  test("an anonymous visitor is redirected away from the dashboard", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
  });

  test("an anonymous visitor cannot reach the admin console", async ({ page }) => {
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/login/);
  });

  test("the admin API refuses an unauthenticated request", async ({ request }) => {
    const response = await request.get("/api/v1/admin/users");
    expect(response.status()).toBe(401);
    const body = await response.json();
    expect(body.error.code).toBe("authentication_required");
    expect(body.error).toHaveProperty("correlation_id");
  });

  test("a guest result API call without a token is refused", async ({ request }) => {
    const created = await request.post("/api/v1/analyses/text", {
      data: { text: ENGLISH_SAMPLE },
    });
    expect(created.status()).toBe(201);
    const analysis = await created.json();

    const withoutToken = await request.get(`/api/v1/analyses/${analysis.id}`);
    expect(withoutToken.status()).toBe(404);

    const withToken = await request.get(
      `/api/v1/analyses/${analysis.id}?token=${analysis.guest_token}`,
    );
    expect(withToken.status()).toBe(200);
  });
});
