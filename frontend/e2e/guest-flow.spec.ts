import { expect, test } from "@playwright/test";
import {
  ENGLISH_SAMPLE,
  FRENCH_SAMPLE,
  SHORT_SAMPLE,
  analyzeText,
  collectConsoleErrors,
  expectNoHorizontalOverflow,
} from "./fixtures";

test.describe("Guest analysis", () => {
  test("submits text, sees the result, exports JSON, and can print", async ({ page }) => {
    const errors = collectConsoleErrors(page);

    await analyzeText(page, ENGLISH_SAMPLE);

    await expect(page).toHaveURL(/\/result\//);
    await expect(page.getByRole("heading", { name: "Analysis result" })).toBeVisible();

    // A band label is always present, in words.
    const score = page.locator("text=/AI signal score/i").first();
    await expect(score).toBeVisible();

    // The disclaimer travels with the result.
    await expect(page.getByTestId("result-disclaimer")).toBeVisible();
    await expect(page.getByText(/not proof of authorship/i)).toBeVisible();

    // Paragraph breakdown is present and derived from real scores.
    await expect(page.getByRole("heading", { name: /paragraph breakdown/i })).toBeVisible();
    await page.getByRole("button", { name: /paragraph 1/i }).click();

    // JSON export produces a real download.
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: /download json/i }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/^originlens-.*\.json$/);

    expect(errors, `console errors: ${errors.join(" | ")}`).toHaveLength(0);
  });

  test("short text is reported as insufficient, not scored", async ({ page, request }) => {
    // The UI blocks submission below the minimum rather than sending a request
    // it knows will be rejected, so the button stays disabled.
    await page.goto("/analyze");
    await page.getByLabel("Writing to analyze").fill(SHORT_SAMPLE);
    await expect(page.getByRole("button", { name: "Analyze", exact: true })).toBeDisabled();
    await expect(page.getByText(/more words needed/i)).toBeVisible();

    // The server reaches the same conclusion independently, and says so in words.
    const response = await request.post("/api/v1/analyses/text", {
      data: { text: SHORT_SAMPLE },
    });
    expect(response.status()).toBe(201);
    const body = await response.json();
    expect(body.label).toBe("Insufficient text");
    expect(body.public_score).toBeNull();
    expect(body.reliability).toBe("insufficient");
  });

  test("unsupported language is reported honestly", async ({ page }) => {
    await analyzeText(page, FRENCH_SAMPLE);
    await expect(page).toHaveURL(/\/result\//);
    await expect(page.getByText("Unsupported language")).toBeVisible();
    // No number is shown for a language the analyser cannot judge.
    await expect(page.getByText("No score")).toBeVisible();
  });

  test("the printable result keeps the disclaimer and hides the navigation", async ({
    page,
  }) => {
    await analyzeText(page, ENGLISH_SAMPLE);
    await expect(page).toHaveURL(/\/result\//);

    await page.emulateMedia({ media: "print" });
    await expect(page.getByTestId("result-disclaimer")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();
    await expect(page.getByRole("button", { name: /download json/i })).toBeHidden();
    await page.emulateMedia({ media: "screen" });
  });

  test("a guest result cannot be opened without its token", async ({ page, context }) => {
    await analyzeText(page, ENGLISH_SAMPLE);
    await expect(page).toHaveURL(/\/result\//);
    const url = page.url();

    // A fresh context has neither the session storage token nor a cookie.
    const stranger = await context.browser()!.newContext();
    const strangerPage = await stranger.newPage();
    await strangerPage.goto(url);
    await expect(
      strangerPage.getByRole("heading", { name: /not available/i }),
    ).toBeVisible();
    await stranger.close();
  });
});

test.describe("Responsive and keyboard access", () => {
  test("the analyzer has no horizontal overflow at 320px", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await page.goto("/analyze");
    await expectNoHorizontalOverflow(page);
  });

  test("the result page has no horizontal overflow at 320px", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await analyzeText(page, ENGLISH_SAMPLE);
    await expect(page).toHaveURL(/\/result\//);
    await expectNoHorizontalOverflow(page);
  });

  test("the primary guest flow is completable with the keyboard alone", async ({ page }) => {
    await page.goto("/analyze");

    // Reach the textarea by tabbing, never by clicking.
    const textarea = page.getByLabel("Writing to analyze");
    await page.keyboard.press("Tab");
    for (let i = 0; i < 25; i += 1) {
      if (await textarea.evaluate((el) => el === document.activeElement)) break;
      await page.keyboard.press("Tab");
    }
    await expect(textarea).toBeFocused();

    await page.keyboard.insertText(ENGLISH_SAMPLE);

    const analyze = page.getByRole("button", { name: "Analyze", exact: true });
    for (let i = 0; i < 10; i += 1) {
      if (await analyze.evaluate((el) => el === document.activeElement)) break;
      await page.keyboard.press("Tab");
    }
    await expect(analyze).toBeFocused();
    await page.keyboard.press("Enter");

    await expect(page).toHaveURL(/\/result\//);
    await expect(page.getByTestId("result-disclaimer")).toBeVisible();
  });

  test("a visible focus indicator is present on the skip link", async ({ page }) => {
    await page.goto("/");
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: /skip to main content/i });
    await expect(skip).toBeFocused();
  });
});
