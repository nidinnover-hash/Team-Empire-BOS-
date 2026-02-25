import { expect, test } from "@playwright/test";

test("dashboard visual baseline", async ({ page }) => {
  await page.goto("/", { waitUntil: "networkidle" });
  await expect(page).toHaveScreenshot("dashboard.png", { fullPage: true });
});
