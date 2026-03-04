import { expect, test } from "@playwright/test";
import { loginForVisuals } from "./auth-utils";

test("integrations visual baseline", async ({ page }) => {
  await loginForVisuals(page);
  await page.goto("/web/integrations", { waitUntil: "networkidle" });
  await expect(page).toHaveURL(/\/web\/integrations$/);
  await expect(page.locator("h1")).toContainText("Integration");
  await expect(page).toHaveScreenshot("integrations.png", { fullPage: true });
});
