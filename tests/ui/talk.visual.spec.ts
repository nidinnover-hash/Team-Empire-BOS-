import { expect, test } from "@playwright/test";
import { loginForVisuals } from "./auth-utils";

test("talk mode visual baseline", async ({ page }) => {
  await loginForVisuals(page);
  await page.goto("/web/talk", { waitUntil: "domcontentloaded" });
  await expect(page).toHaveURL(/\/web\/talk$/);
  await expect(page.locator(".talk-header .title")).toContainText("Talk to Agent");
  await expect(page).toHaveScreenshot("talk.png", { fullPage: true });
});
