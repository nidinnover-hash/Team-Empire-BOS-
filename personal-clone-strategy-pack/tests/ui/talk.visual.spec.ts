import { expect, test } from "@playwright/test";

test("talk mode visual baseline", async ({ page }) => {
  await page.goto("/web/talk", { waitUntil: "networkidle" });
  await expect(page).toHaveScreenshot("talk.png", { fullPage: true });
});
