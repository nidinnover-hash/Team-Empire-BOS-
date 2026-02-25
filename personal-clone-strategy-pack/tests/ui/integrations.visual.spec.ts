import { expect, test } from "@playwright/test";

test("integrations visual baseline", async ({ page }) => {
  await page.goto("/web/integrations", { waitUntil: "networkidle" });
  await expect(page).toHaveScreenshot("integrations.png", { fullPage: true });
});
