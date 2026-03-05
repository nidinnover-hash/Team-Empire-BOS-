import { expect, test } from "@playwright/test";
import { loginForVisuals } from "./auth-utils";

test("dashboard visual baseline", async ({ page }) => {
  await loginForVisuals(page);
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator("main.dash")).toBeVisible();
  await expect(page).toHaveScreenshot("dashboard.png", { fullPage: true });
});
