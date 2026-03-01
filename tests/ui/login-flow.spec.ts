import { expect, test } from "@playwright/test";

test.describe("Login flow", () => {
  test("shows error on invalid credentials", async ({ page }) => {
    await page.goto("/web/login", { waitUntil: "domcontentloaded" });

    await page.fill('input[name="email"], input[type="email"]', "invalid@example.com");
    await page.fill('input[name="password"], input[type="password"]', "wrongpassword");
    await page.click('button[type="submit"]');

    // Should stay on login page or show error
    await page.waitForTimeout(1000);
    expect(page.url()).toContain("/web/login");
  });

  test("login page has required form elements", async ({ page }) => {
    await page.goto("/web/login", { waitUntil: "domcontentloaded" });

    const emailInput = page.locator('input[name="email"], input[type="email"]');
    const passwordInput = page.locator('input[name="password"], input[type="password"]');
    const submitBtn = page.locator('button[type="submit"]');

    await expect(emailInput).toBeVisible();
    await expect(passwordInput).toBeVisible();
    await expect(submitBtn).toBeVisible();
  });
});
