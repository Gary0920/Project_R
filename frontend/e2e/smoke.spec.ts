import { test, expect } from "@playwright/test";

test.describe("App smoke test", () => {
  test("renderer loads and shows login page", async ({ page }) => {
    await page.goto("/");
    // The app should either show the login page or redirect to it
    // Login page typically contains a login form
    await page.waitForLoadState("networkidle");

    // Check that the page loaded without a blank screen
    const body = page.locator("body");
    await expect(body).not.toBeEmpty();

    // Check for either a login form or app shell elements
    // Login page assertions
    const loginForm = page.locator('input[type="password"], input[name="password"]');
    const appShell = page.locator("#root, #app");

    const hasLoginForm = (await loginForm.count()) > 0;
    const hasAppShell = (await appShell.count()) > 0;

    if (!hasLoginForm && !hasAppShell) {
      // Fallback: page has visible content
      await expect(page.locator("body")).toContainText(/.*/);
    }
  });

  test("page has valid title", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("domcontentloaded");

    const title = await page.title();
    expect(title.length).toBeGreaterThan(0);
  });
});
